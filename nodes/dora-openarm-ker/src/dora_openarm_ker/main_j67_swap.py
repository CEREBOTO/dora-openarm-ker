# Copyright 2026 Enactic, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""dora-rs KER leader with J6/J7 remapped to follower J7/J6."""

import argparse
import json
import time

import dora
import numpy as np
import pyarrow as pa
from openarm_ker.ker_stream import CMD_STANDBY, CMD_STREAM, KERStream

from dora_openarm_ker.main import KerPoseProcessor, map_range

# Measured on left follower gripper motor (can1, ID 8): open / closed (rad).
GRIP_L_FOLLOWER_OPEN_RAD = -1.193
GRIP_L_FOLLOWER_CLOSED_RAD = 0.0
GRIP_L_KER_OPEN_DEG = 0.0
GRIP_L_KER_CLOSED_DEG = 60.0


def _map_ker_joints_to_follower(arm_deg: list[float]) -> list[float]:
    """Map KER J1-J7 (deg) to follower J1-J7 (deg) with wrist swap and ±45 deg clamp."""
    ker_j6, ker_j7 = arm_deg[5], arm_deg[6]
    # KER J7 -> follower J6: clamp KER to -45..45, map 1:1 to follower J6
    follower_j6 = map_range(ker_j7, -45.0, 45.0, -45.0, 45.0)
    # KER J6 -> follower J7: clamp KER to -45..45, invert direction, map to follower J7
    follower_j7 = map_range(ker_j6, -45.0, 45.0, 45.0, -45.0)
    return arm_deg[:5] + [follower_j6, follower_j7]


class KerPoseProcessorJ67Swap(KerPoseProcessor):
    """Same as KerPoseProcessor, but KER J6->follower J7 and KER J7->follower J6."""

    def process(self, raw_angles: list[float]) -> tuple[list[float], list[float]]:
        filtered = self.hampel.process(raw_angles) if self.hampel else raw_angles

        grip_r_deg = map_range(filtered[7], 0.0, -60.0, -60.0, 10.0)
        grip_l_rad = map_range(
            filtered[15],
            GRIP_L_KER_OPEN_DEG,
            GRIP_L_KER_CLOSED_DEG,
            GRIP_L_FOLLOWER_OPEN_RAD,
            GRIP_L_FOLLOWER_CLOSED_RAD,
        )

        pos_right = np.deg2rad(_map_ker_joints_to_follower(filtered[:7])).tolist()
        pos_right.append(np.deg2rad(grip_r_deg))

        pos_left = np.deg2rad(_map_ker_joints_to_follower(filtered[8:15])).tolist()
        pos_left.append(grip_l_rad)

        return pos_right, pos_left


def main():
    """Act OpenArm KER as a leader of OpenArm (J6/J7 swap variant)."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--hampel", action="store_true", help="Enable Hampel filter")
    args = parser.parse_args()

    print("Connecting to KER device (J6/J7 swap mapping)...")
    stream = KERStream()
    stream.connect()
    stream.send_command(CMD_STREAM)

    print("\n=== Verified Device Metadata ===")
    print(f" Hardware : {stream.metadata.get('hw')}")
    print(f" Firmware : {stream.metadata.get('fw')}")
    print(f" Updated  : {stream.metadata.get('updated')}")
    print(" Mapping  : KER J7->follower J6 (-45..+45), KER J6->follower J7 (-45..+45, inverted)")
    print("            right gripper: KER 0..-60 -> follower -60..+10 deg")
    print("            left gripper:  KER 0..+60 deg -> follower -1.193..0 rad")
    print("================================\n")

    print("Initializing dora-rs node...")
    node = dora.Node()
    processor = KerPoseProcessorJ67Swap(use_hampel=args.hampel)

    print("KER Leader Node (J6/J7 swap) running.\n")
    node.send_output(
        "metadata",
        pa.array([json.dumps(stream.metadata)]),
        {"timestamp": time.time_ns()},
    )
    try:
        for event in node:
            if event["type"] == "ERROR":
                print(f"Dora error occurred: {event['error']}")
                break

            elif event["type"] == "STOP":
                print("Received STOP event from dora. Shutting down...")
                break

            if event["type"] != "INPUT":
                continue

            data = stream.recv()
            if data is None:
                continue

            pos_right, pos_left = processor.process(data["angles"])

            ts = {"timestamp": time.time_ns()}

            node.send_output(
                "follower_position_right", pa.array(pos_right, type=pa.float32()), ts
            )
            node.send_output(
                "follower_position_left", pa.array(pos_left, type=pa.float32()), ts
            )

    except KeyboardInterrupt:
        pass

    finally:
        try:
            print("\nShutting down: Sending STANDBY command...")
            stream.send_command(CMD_STANDBY)
            time.sleep(0.1)
        except Exception:
            pass
        stream.close()
        print("KER Leader Node Disconnected safely.")


if __name__ == "__main__":
    main()

    

