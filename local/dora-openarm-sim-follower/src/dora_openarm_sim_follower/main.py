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
# See the License under the License.

"""Sim follower with the same align / slow-start behavior as dora-openarm."""

import argparse
import dataclasses
import enum
import time

import dora
import numpy as np
import pyarrow as pa

# Matches openarm_driver configs/openarm_cell.yaml start/stop poses.
ArrayLike = np.ndarray | list[float]

START_POSES = {
    "right_arm": np.array(
        [0.0, 0.0, 0.0, 1.5707963267948966, 0.0, 0.0, 0.0, 0.0], dtype=np.float32
    ),
    "left_arm": np.array(
        [0.0, 0.0, 0.0, 1.5707963267948966, 0.0, 0.0, 0.0, 0.0], dtype=np.float32
    ),
}


class ArmStatus(str, enum.Enum):
    STOPPED = "stopped"
    STARTED = "started"
    ALIGNED = "aligned"


@dataclasses.dataclass
class AlignState:
    align_target: np.ndarray | None = None
    step_limit: float = 0.001


class SimArm:
    """Tracks simulated joint state and publishes position commands."""

    def __init__(self, side: str, node: dora.Node):
        self.arm_side = side
        self.node = node
        self.last_command = START_POSES[side].copy()
        self._observation = START_POSES[side].copy()

    def update_observation(self, qpos: np.ndarray) -> None:
        self._observation = np.asarray(qpos, dtype=np.float32)
        self.last_command = self._observation.copy()

    def fetch_position(self) -> np.ndarray:
        return self._observation.copy()

    def send_position(self, position: ArrayLike) -> None:
        target = np.asarray(position, dtype=np.float32)
        self.last_command = target.copy()
        self._observation = target.copy()
        self.node.send_output("position", pa.array(target, type=pa.float32()))

    def smooth_move(self, position: ArrayLike, hz: int = 50, duration: float = 2.0) -> None:
        target = np.asarray(position, dtype=np.float32)
        num_steps = max(1, int(hz * duration))
        start = self.fetch_position()
        for step in range(1, num_steps + 1):
            alpha = step / num_steps
            interpolated = start * (1.0 - alpha) + target * alpha
            self.send_position(interpolated)
            time.sleep(1.0 / hz)


def _align(arm: SimArm, state: AlignState, new_position, name: str, threshold: float, trigger=None):
    if trigger == "gripper":
        gripper_position = new_position[-1]
        if name == "right_arm":
            is_gripping = gripper_position.as_py() > np.deg2rad(-5)
        elif name == "left_arm":
            is_gripping = gripper_position.as_py() < np.deg2rad(5)
        else:
            is_gripping = False
        if not is_gripping:
            return False

    def current_position():
        return arm.fetch_position()

    if state.align_target is None:
        state.align_target = current_position().copy()

    def is_aligned(position1, position2):
        return np.all(np.abs(position1 - position2) < threshold)

    current = current_position()
    target = np.asarray(new_position, dtype=np.float32)
    if is_aligned(target, current):
        return True

    diff = target - state.align_target
    step_move = np.clip(diff, -state.step_limit, state.step_limit)
    state.align_target = state.align_target + step_move
    arm.send_position(state.align_target)
    return is_aligned(target, arm.fetch_position())


def main():
    parser = argparse.ArgumentParser(description="Sim follower with align for MuJoCo")
    parser.add_argument("--side", choices=["right", "left"], default="right")
    parser.add_argument(
        "--align-trigger",
        choices=["gripper"],
        default=None,
    )
    parser.add_argument("--align-threshold", default=0.1, type=float)
    args = parser.parse_args()

    node = dora.Node()
    name = f"{args.side}_arm"
    arm = SimArm(name, node)
    status = ArmStatus.STOPPED
    align_state = AlignState()
    align_threshold = args.align_threshold

    node.send_output("status", pa.array([ArmStatus.STOPPED.value]))

    for event in node:
        if event["type"] != "INPUT":
            continue

        event_id = event["id"]
        if event_id == "observation":
            arm.update_observation(np.asarray(event["value"], dtype=np.float32))
        elif event_id == "command":
            command = event["value"][0].as_py()
            if command == "start":
                arm.smooth_move(START_POSES[name], hz=50, duration=2.0)
                align_state = AlignState()
                status = ArmStatus.STARTED
                node.send_output("status", pa.array([ArmStatus.STARTED.value]))
            elif command == "stop":
                arm.smooth_move(START_POSES[name], hz=50, duration=2.0)
                status = ArmStatus.STOPPED
                node.send_output("status", pa.array([ArmStatus.STOPPED.value]))
        elif event_id == "move_position":
            if status is ArmStatus.STOPPED:
                continue

            value = event["value"]
            if isinstance(value, pa.StructArray):
                new_position = value.field("new_position")
            else:
                new_position = value

            target = np.asarray(new_position, dtype=np.float32)

            if status is ArmStatus.ALIGNED:
                diverged = np.any(
                    np.abs(target[:-1] - arm.last_command[:-1]) > align_threshold
                )
                if diverged:
                    status = ArmStatus.STARTED
                    align_state = AlignState()
                    node.send_output("status", pa.array([ArmStatus.STARTED.value]))
                else:
                    arm.send_position(target)

            if status is ArmStatus.STARTED:
                if _align(
                    arm,
                    align_state,
                    new_position,
                    name,
                    align_threshold,
                    trigger=args.align_trigger,
                ):
                    status = ArmStatus.ALIGNED
                    node.send_output("status", pa.array([ArmStatus.ALIGNED.value]))


if __name__ == "__main__":
    main()
