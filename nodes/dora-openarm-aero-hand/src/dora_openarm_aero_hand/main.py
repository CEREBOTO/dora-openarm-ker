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

"""Map the KER right trigger to an Aero Hand grip. No arm alignment."""

import argparse
import time

import dora
import numpy as np
from aero_open_sdk.aero_hand import AeroHand

# Grip matches the aero-open-gui sliders: abduction and tendon at 1.0,
# thumb flex at 0.0, and the four fingers at 1.0.
OPEN_POSE = [100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
GRIP_POSE = [100.0, 0.0, 90.0, 90.0, 90.0, 90.0, 90.0]

# KER leader maps the right trigger encoder onto this gripper-angle range.
RELEASED_RAD = float(np.deg2rad(-60.0))
PRESSED_RAD = float(np.deg2rad(10.0))
SEND_INTERVAL_S = 0.02


def _gripper_rad(value) -> float:
    position = np.asarray(value, dtype=np.float32).reshape(-1)
    return float(position[-1])


def _pose_from_trigger(gripper_rad: float) -> list[float]:
    span = PRESSED_RAD - RELEASED_RAD
    amount = (gripper_rad - RELEASED_RAD) / span
    amount = min(1.0, max(0.0, amount))
    if amount < 0.05:
        amount = 0.0
    return [open_ + amount * (closed - open_) for open_, closed in zip(OPEN_POSE, GRIP_POSE)]


def _prepare_hand(hand: AeroHand) -> None:
    """Set a gentle speed and torque. Keep going if the firmware does not ACK."""
    for actuator_id in range(7):
        try:
            hand.set_speed(actuator_id, 80)
            time.sleep(0.01)
            hand.set_torque(actuator_id, 400)
            time.sleep(0.01)
        except (TimeoutError, OSError) as exc:
            print(
                f"Aero Hand kept default speed/torque "
                f"(actuator {actuator_id} did not ACK: {exc})"
            )
            return


def main() -> None:
    """Follow the last value of the leader position and ignore arm alignment."""
    parser = argparse.ArgumentParser(description="Aero Hand grip from a KER trigger")
    parser.add_argument("--port", default=None, help="Serial port. Auto-detect if omitted.")
    args = parser.parse_args()

    node = dora.Node()
    hand = AeroHand(port=args.port)
    _prepare_hand(hand)
    hand.set_joint_positions(OPEN_POSE)
    last_sent = 0.0
    try:
        for event in node:
            if event["type"] != "INPUT":
                continue
            if event["id"] != "gripper":
                continue
            now = time.monotonic()
            if now - last_sent < SEND_INTERVAL_S:
                continue
            last_sent = now
            hand.set_joint_positions(_pose_from_trigger(_gripper_rad(event["value"])))
    finally:
        try:
            hand.set_joint_positions(OPEN_POSE)
        finally:
            hand.close()


if __name__ == "__main__":
    main()
