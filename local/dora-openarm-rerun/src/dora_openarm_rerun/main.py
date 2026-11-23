"""Log arm positions and camera frames to a Rerun window.

Left joints share one plot and right joints share another. Only the follower's
measured joint positions are drawn. Inputs whose ids start with ``camera_``
are images.
"""

import os

import pyarrow as pa
import rerun as rr
import rerun.blueprint as rrb

import dora

_JOINT_NAMES = ("J1", "J2", "J3", "J4", "J5", "J6", "J7", "gripper")
_JPEG_TYPES = {"jpeg", "jpg", "jpe"}


def _positions(value) -> list[float]:
    value_type = getattr(value, "type", None)
    if value_type is not None and pa.types.is_struct(value_type):
        return [float(row["qpos"]) for row in value.to_pylist()]
    data = value.to_pylist() if hasattr(value, "to_pylist") else list(value)
    if data and isinstance(data[0], dict) and "qpos" in data[0]:
        return [float(row["qpos"]) for row in data]
    return [float(item) for item in data]


def _log_series(event_id: str, value) -> None:
    if not event_id.startswith("observation_"):
        return
    side = event_id.removeprefix("observation_")
    for index, sample in enumerate(_positions(value)):
        name = _JOINT_NAMES[index] if index < len(_JOINT_NAMES) else f"j{index}"
        rr.log(f"arm/{side}/{name}", rr.Scalars(sample))


def _blueprint() -> rrb.Blueprint:
    """Six views: two small arm plots, then four larger camera images."""
    return rrb.Blueprint(
        rrb.Vertical(
            rrb.Horizontal(
                rrb.TimeSeriesView(origin="/arm/left", name="Left arm"),
                rrb.TimeSeriesView(origin="/arm/right", name="Right arm"),
            ),
            rrb.Horizontal(
                rrb.Spatial2DView(contents="camera/head_left", name="Head L"),
                rrb.Spatial2DView(contents="camera/head_right", name="Head R"),
            ),
            rrb.Horizontal(
                rrb.Spatial2DView(contents="camera/wrist_left", name="Wrist L"),
                rrb.Spatial2DView(contents="camera/wrist_right", name="Wrist R"),
            ),
            row_shares=[1, 3, 3],
        )
    )


def _log_image(event_id: str, value, metadata) -> None:
    encoding = str((metadata or {}).get("encoding", "")).lower()
    raw = value.to_numpy(zero_copy_only=False).reshape(-1)
    path = f"camera/{event_id.removeprefix('camera_')}"
    if encoding in _JPEG_TYPES or (raw.size > 2 and int(raw[0]) == 0xFF and int(raw[1]) == 0xD8):
        rr.log(path, rr.EncodedImage(contents=raw.tobytes(), media_type="image/jpeg"))
        return
    width = int((metadata or {}).get("width") or 0)
    height = int((metadata or {}).get("height") or 0)
    if encoding in ("bgr8", "rgb8") and width > 0 and height > 0:
        image = raw.reshape(height, width, 3)
        if encoding == "bgr8":
            image = image[:, :, ::-1]
        rr.log(path, rr.Image(image))
        return
    print(f"[rerun] Skipping {event_id}: encoding {encoding or 'unknown'}")


def main() -> None:
    # The viewer runs on the host. The container only sends data to it.
    url = os.environ.get("RERUN_URL", "rerun+http://127.0.0.1:9876/proxy")
    try:
        rr.init("openarm-teleop")
        if hasattr(rr, "connect_grpc"):
            rr.connect_grpc(url)
        else:
            rr.connect(url)
        rr.send_blueprint(_blueprint())
    except Exception as exc:
        raise SystemExit(f"[rerun] Could not connect to {url}: {exc}") from exc
    print(f"[rerun] Connected to {url}")

    node = dora.Node()
    for event in node:
        if event["type"] == "STOP":
            break
        if event["type"] != "INPUT":
            continue
        event_id = event["id"]
        if event_id.startswith("camera_"):
            _log_image(event_id, event["value"], event.get("metadata"))
        elif event_id.startswith("observation_"):
            _log_series(event_id, event["value"])


if __name__ == "__main__":
    main()
