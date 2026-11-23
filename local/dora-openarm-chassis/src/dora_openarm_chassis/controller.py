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

"""Convert Quest thumbstick axes into SocketCAN CtrlCmd frames for the chassis."""

import argparse
import socket
import struct

import dora
import numpy as np
import pyarrow as pa

_GEAR_PARK = 1
_GEAR_FOUR_WHEEL_STEER = 6
_CAN_ID_CTRL_CMD = 0x98C4D1D0
_CAN_FRAME_FMT = "<IB3x8s"

AF_CAN = 29
PF_CAN = AF_CAN
CAN_RAW = 1

_count = 0


def _open_can_socket(if_name: str) -> socket.socket:
    sock = socket.socket(PF_CAN, socket.SOCK_RAW, CAN_RAW)
    sock.bind((if_name,))
    return sock


def _encode_ctrl_cmd(gear: int, x_linear: float, y_linear: float, z_angular: float) -> bytes:
    global _count

    x = int(x_linear * 1000)
    y = int(y_linear * 1000)
    z = int(z_angular * 100)

    d = bytearray(8)
    d[0] = (gear & 0x0F) | ((x & 0x0F) << 4)
    d[1] = (x >> 4) & 0xFF
    d[2] = ((x >> 12) & 0x0F) | ((z & 0x0F) << 4)
    d[3] = (z >> 4) & 0xFF
    d[4] = ((z >> 12) & 0x0F) | ((y & 0x0F) << 4)
    d[5] = (y >> 4) & 0xFF
    _count = (_count + 1) & 0x0F
    d[6] = ((y >> 12) & 0x0F) | (_count << 4)
    d[7] = d[0] ^ d[1] ^ d[2] ^ d[3] ^ d[4] ^ d[5] ^ d[6]
    return bytes(d)


def _run(args: argparse.Namespace) -> None:
    deadzone = args.deadzone
    max_linear = args.max_linear
    max_angular = args.max_angular
    can_if = args.can_if

    can_sock = _open_can_socket(can_if)
    print(f"[chassis-controller] Opened {can_if}")

    node = dora.Node()
    node.send_output("status", pa.array(["ready"]))

    prev_left_stick_y = 0.0
    prev_right_stick_x = 0.0

    try:
        for event in node:
            if event["type"] == "INPUT":
                if event["id"] == "left_stick_y":
                    prev_left_stick_y = float(event["value"][0].as_py())
                elif event["id"] == "right_stick_x":
                    prev_right_stick_x = float(event["value"][0].as_py())
                elif event["id"] != "tick":
                    continue

            if event["type"] == "STOP":
                break

            if event["id"] != "tick":
                continue

            left_val = prev_left_stick_y
            right_val = prev_right_stick_x

            if abs(left_val) < deadzone and abs(right_val) < deadzone:
                gear = _GEAR_PARK
                x_lin = 0.0
                z_ang = 0.0
            else:
                gear = _GEAR_FOUR_WHEEL_STEER
                x_lin = float(np.clip(left_val * max_linear, -max_linear, max_linear))
                z_ang = float(np.clip(-right_val * max_angular, -max_angular, max_angular))

            payload = _encode_ctrl_cmd(gear, x_lin, 0.0, z_ang)
            frame = struct.pack(_CAN_FRAME_FMT, _CAN_ID_CTRL_CMD, 8, payload)
            try:
                can_sock.send(frame)
            except OSError:
                pass

    finally:
        payload = _encode_ctrl_cmd(_GEAR_PARK, 0.0, 0.0, 0.0)
        frame = struct.pack(_CAN_FRAME_FMT, _CAN_ID_CTRL_CMD, 8, payload)
        try:
            can_sock.send(frame)
        except OSError:
            pass
        can_sock.close()
        print("[chassis-controller] CAN socket closed")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Chassis teleop: joysticks → SocketCAN (dora node, no ROS 2)",
    )
    parser.add_argument("--can-if", default="can2", help="SocketCAN interface name")
    parser.add_argument("--max-linear", type=float, default=0.3, help="Max forward speed (m/s)")
    parser.add_argument("--max-angular", type=float, default=40.0, help="Max steering speed (deg/s)")
    parser.add_argument("--deadzone", type=float, default=0.05, help="Joystick deadzone threshold")
    args = parser.parse_args()
    _run(args)


if __name__ == "__main__":
    main()
