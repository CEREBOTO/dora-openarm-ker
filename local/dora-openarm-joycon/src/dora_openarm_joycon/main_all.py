"""Both Joy-Cons: grippers, chassis, and lift.

The left stick's horizontal axis steers the chassis. The right stick's
vertical axis drives it forward and back. Left D-pad up and down move the
lift. ZL closes the left gripper and ZR closes the right gripper. B on the
right Joy-Con interrupts dora the same way Ctrl+C does in the terminal.
"""

import argparse
import math
import os
import signal
from pathlib import Path

import dora
import pyarrow as pa

from dora_openarm_joycon.main import _ABS_RX, _ABS_RY, _JoyCon, _gripper_angle


def _proc_fields(pid: int) -> list[str] | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        return stat.rsplit(")", 1)[1].split()
    except (OSError, IndexError, ValueError):
        return None


def _cmdline(pid: int) -> list[str]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except OSError:
        return []
    return [part.decode(errors="replace") for part in raw if part]


def _is_dora_command(args: list[str]) -> bool:
    # `.venv/bin/dora` is a Python script, so argv[0] is python3 and argv[1] is dora.
    return any(Path(arg).name == "dora" for arg in args[:3])


def _dora_supervisor_pid() -> int | None:
    """Return the outermost dora process above this node."""
    pid = os.getpid()
    found = None
    seen: set[int] = set()
    while pid > 1 and pid not in seen:
        seen.add(pid)
        fields = _proc_fields(pid)
        if fields is None or len(fields) < 2:
            break
        ppid = int(fields[1])
        if _is_dora_command(_cmdline(ppid)):
            found = ppid
        pid = ppid
    return found


def _stop_like_ctrl_c() -> None:
    """Interrupt the dataflow the same way Ctrl+C does in the terminal."""
    fields = _proc_fields(os.getpid())
    tpgid = int(fields[5]) if fields is not None and len(fields) > 5 else -1
    if tpgid > 1:
        print("[joycon] B pressed, stopping the dataflow")
        os.killpg(tpgid, signal.SIGINT)
        return

    pid = _dora_supervisor_pid()
    if pid is None:
        print("[joycon] B pressed, but no dora process was found")
        return
    print("[joycon] B pressed, stopping the dataflow")
    os.killpg(os.getpgid(pid), signal.SIGINT)


def _replace_gripper(event, closed: bool, open_rad: float, close_rad: float, connected: bool):
    values = event["value"].to_pylist()
    if values and connected:
        values[-1] = _gripper_angle(closed, open_rad, close_rad)
    return pa.array(values, type=pa.float32())


def _run(args: argparse.Namespace) -> None:
    left = _JoyCon(args.left_name, args.deadzone)
    # The right Joy-Con stick is ABS_RX/ABS_RY. ABS_X/ABS_Y belong to the left one.
    right = _JoyCon(args.right_name, args.deadzone, axis_x=_ABS_RX, axis_y=_ABS_RY)
    left_open = math.radians(args.left_open_deg)
    left_close = math.radians(args.left_close_deg)
    right_open = math.radians(args.right_open_deg)
    right_close = math.radians(args.right_close_deg)
    node = dora.Node()
    left_missing = False
    right_missing = False

    try:
        for event in node:
            if event["type"] == "STOP":
                break
            if event["type"] != "INPUT":
                continue

            left.poll()
            right.poll()
            if right.b_pressed:
                _stop_like_ctrl_c()
                break
            if not left.connected and not left_missing:
                print(f"[joycon] Waiting for {args.left_name}")
                left_missing = True
            elif left.connected:
                left_missing = False
            if not right.connected and not right_missing:
                print(f"[joycon] Waiting for {args.right_name}")
                right_missing = True
            elif right.connected:
                right_missing = False

            event_id = event["id"]
            metadata = event["metadata"]
            if event_id == "arm_position_left":
                node.send_output(
                    "arm_position_left",
                    _replace_gripper(event, left.zl, left_open, left_close, left.connected),
                    metadata,
                )
            elif event_id == "arm_position_right":
                node.send_output(
                    "arm_position_right",
                    _replace_gripper(event, right.zr, right_open, right_close, right.connected),
                    metadata,
                )
            elif event_id == "tick":
                _forward, turn = left.axes()
                forward, _turn = right.axes()
                if not left.connected:
                    turn = 0.0
                if not right.connected:
                    forward = 0.0
                node.send_output("left_stick_y", pa.array([forward], type=pa.float32()), metadata)
                node.send_output("right_stick_x", pa.array([turn], type=pa.float32()), metadata)
                node.send_output("button_x", pa.array([left.up], type=pa.bool_()), metadata)
                node.send_output("button_y", pa.array([left.down], type=pa.bool_()), metadata)
    finally:
        left.close()
        right.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Both Joy-Cons for arms, chassis, and lift")
    parser.add_argument("--left-name", default="Joy-Con (L)", help="Left input device name")
    parser.add_argument("--right-name", default="Joy-Con (R)", help="Right input device name")
    parser.add_argument("--deadzone", type=float, default=0.08, help="Stick deadzone, 0 to 1")
    parser.add_argument("--left-open-deg", type=float, default=60.0, help="Left gripper open angle")
    parser.add_argument("--left-close-deg", type=float, default=-10.0, help="Left gripper closed angle")
    parser.add_argument("--right-open-deg", type=float, default=-60.0, help="Right gripper open angle")
    parser.add_argument("--right-close-deg", type=float, default=10.0, help="Right gripper closed angle")
    _run(parser.parse_args())


if __name__ == "__main__":
    main()
