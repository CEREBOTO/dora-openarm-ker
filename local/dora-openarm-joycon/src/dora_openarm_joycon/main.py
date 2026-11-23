"""Read a left Joy-Con and publish chassis, lift, and left-gripper commands.

The kernel hid-nintendo driver already exposes the controller as an input
device. Stick up is a negative ABS_Y, matching the Linux gamepad spec, so the
vertical axis is flipped before it is sent as chassis forward speed.
"""

import argparse
import fcntl
import math
import os
import struct
from pathlib import Path

import dora
import pyarrow as pa

_EVENT = struct.Struct("llHHi")
_EV_KEY = 1
_EV_ABS = 3
_ABS_X = 0
_ABS_Y = 1
_ABS_RX = 3
_ABS_RY = 4
_BTN_B = 304  # BTN_SOUTH, the B button on Joy-Con (R)
_BTN_ZL = 312  # BTN_TL2
_BTN_ZR = 313  # BTN_TR2
_BTN_UP = 544  # BTN_DPAD_UP
_BTN_DOWN = 545  # BTN_DPAD_DOWN
_STICK_FULL_SCALE = 32767.0


def _eviocgabs(axis: int) -> int:
    return (2 << 30) | (24 << 16) | (ord("E") << 8) | (0x40 + axis)


def _eviocgkey(size: int) -> int:
    return (2 << 30) | (size << 16) | (ord("E") << 8) | 0x18


def _find_device(name: str) -> str | None:
    for event in sorted(Path("/dev/input").glob("event*")):
        sysfs_name = Path(f"/sys/class/input/{event.name}/device/name")
        try:
            current = sysfs_name.read_text(encoding="ascii").strip()
        except OSError:
            continue
        if current == name:
            return str(event)
    return None


def _button_down(bitmap: bytes, code: int) -> bool:
    return bool(bitmap[code // 8] & (1 << (code % 8)))


def _normalize(raw: float, deadzone: float) -> float:
    value = max(-1.0, min(1.0, raw / _STICK_FULL_SCALE))
    if abs(value) < deadzone:
        return 0.0
    sign = 1.0 if value > 0.0 else -1.0
    return sign * (abs(value) - deadzone) / (1.0 - deadzone)


class _JoyCon:
    def __init__(self, name: str, deadzone: float, axis_x: int = _ABS_X, axis_y: int = _ABS_Y):
        self._name = name
        self._deadzone = deadzone
        self._axis_x = axis_x
        self._axis_y = axis_y
        self._fd: int | None = None
        self._path: str | None = None
        self._raw_x = 0
        self._raw_y = 0
        self.zl = False
        self.zr = False
        self.b = False
        self.b_pressed = False
        self.up = False
        self.down = False

    def open(self) -> bool:
        if self._fd is not None:
            return True
        path = _find_device(self._name)
        if path is None:
            return False
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            self._seed(fd)
        except OSError as exc:
            print(f"[joycon] Could not open {path}: {exc}")
            return False
        self._fd = fd
        self._path = path
        print(f"[joycon] Opened {self._name} at {path}")
        return True

    def close(self) -> None:
        if self._fd is None:
            return
        os.close(self._fd)
        self._fd = None
        self._path = None
        self._raw_x = 0
        self._raw_y = 0
        self.zl = False
        self.zr = False
        self.b = False
        self.b_pressed = False
        self.up = False
        self.down = False

    @property
    def connected(self) -> bool:
        return self._fd is not None

    def poll(self) -> None:
        self.b_pressed = False
        if self._fd is None and not self.open():
            return
        assert self._fd is not None
        while True:
            try:
                packet = os.read(self._fd, _EVENT.size * 64)
            except BlockingIOError:
                return
            except OSError as exc:
                print(f"[joycon] Read failed on {self._path}: {exc}")
                self.close()
                return
            if not packet:
                return
            for offset in range(0, len(packet) - _EVENT.size + 1, _EVENT.size):
                _sec, _usec, event_type, code, value = _EVENT.unpack_from(packet, offset)
                self._apply(event_type, code, value)

    def axes(self) -> tuple[float, float]:
        # Stick up is negative ABS_Y. Chassis forward is positive.
        forward = _normalize(-self._raw_y, self._deadzone)
        turn = _normalize(self._raw_x, self._deadzone)
        return forward, turn

    def _seed(self, fd: int) -> None:
        for axis, slot in ((self._axis_x, "x"), (self._axis_y, "y")):
            info = bytearray(24)
            fcntl.ioctl(fd, _eviocgabs(axis), info)
            raw = struct.unpack_from("i", info)[0]
            if slot == "x":
                self._raw_x = raw
            else:
                self._raw_y = raw
        bitmap = bytearray(128)
        fcntl.ioctl(fd, _eviocgkey(len(bitmap)), bitmap)
        self.zl = _button_down(bitmap, _BTN_ZL)
        self.zr = _button_down(bitmap, _BTN_ZR)
        self.b = _button_down(bitmap, _BTN_B)
        self.up = _button_down(bitmap, _BTN_UP)
        self.down = _button_down(bitmap, _BTN_DOWN)

    def _apply(self, event_type: int, code: int, value: int) -> None:
        if event_type == _EV_ABS:
            if code == self._axis_x:
                self._raw_x = value
            elif code == self._axis_y:
                self._raw_y = value
            return
        if event_type != _EV_KEY:
            return
        pressed = value != 0
        if code == _BTN_B:
            if value == 1 and not self.b:
                self.b_pressed = True
            self.b = pressed
        elif code == _BTN_ZL:
            self.zl = pressed
        elif code == _BTN_ZR:
            self.zr = pressed
        elif code == _BTN_UP:
            self.up = pressed
        elif code == _BTN_DOWN:
            self.down = pressed


def _gripper_angle(closed: bool, open_rad: float, close_rad: float) -> float:
    return close_rad if closed else open_rad


def _run(args: argparse.Namespace) -> None:
    joycon = _JoyCon(args.name, args.deadzone)
    open_rad = math.radians(args.open_deg)
    close_rad = math.radians(args.close_deg)
    node = dora.Node()
    missing_announced = False

    try:
        for event in node:
            if event["type"] == "STOP":
                break
            if event["type"] != "INPUT":
                continue

            joycon.poll()
            if not joycon.connected and not missing_announced:
                print(f"[joycon] Waiting for {args.name}")
                missing_announced = True
            elif joycon.connected:
                missing_announced = False

            event_id = event["id"]
            metadata = event["metadata"]
            if event_id == "arm_position":
                values = event["value"].to_pylist()
                if values and joycon.connected:
                    values[-1] = _gripper_angle(joycon.zl, open_rad, close_rad)
                node.send_output("arm_position", pa.array(values, type=pa.float32()), metadata)
            elif event_id == "tick":
                forward, turn = joycon.axes()
                node.send_output("left_stick_y", pa.array([forward], type=pa.float32()), metadata)
                node.send_output("right_stick_x", pa.array([turn], type=pa.float32()), metadata)
                node.send_output("button_x", pa.array([joycon.up], type=pa.bool_()), metadata)
                node.send_output("button_y", pa.array([joycon.down], type=pa.bool_()), metadata)
    finally:
        joycon.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Left Joy-Con to chassis, lift, and gripper")
    parser.add_argument("--name", default="Joy-Con (L)", help="Input device name")
    parser.add_argument("--deadzone", type=float, default=0.08, help="Stick deadzone, 0 to 1")
    parser.add_argument("--open-deg", type=float, default=60.0, help="Left gripper open angle")
    parser.add_argument("--close-deg", type=float, default=-10.0, help="Left gripper closed angle")
    _run(parser.parse_args())


if __name__ == "__main__":
    main()
