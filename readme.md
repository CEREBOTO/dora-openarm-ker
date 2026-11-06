# KER 遥操作启动

```bash
cd /home/cereboto/worktest/dora-openarm-data-collection
```

## 前置

| 模式 | 需要 |
|------|------|
| 仿真 | KER USB |
| 真机 | KER USB + CAN（`openarm-can-cli can_configure`） |

Web UI：http://127.0.0.1:8000 → **Start Arm** 启动从臂，**Start!** 仅录制版有。

---

## 仿真（MuJoCo）

```bash
.venv/bin/dora build dataflow-ker-mujoco.yaml --uv
.venv/bin/dora run dataflow-ker-mujoco.yaml --uv
```

---

## 真机 · 原版（J6↔J6，J7↔J7）

```bash
# 双臂
.venv/bin/dora build dataflow-ker-bimanual.yaml --uv
.venv/bin/dora run dataflow-ker-bimanual.yaml --uv

# 双臂 + 相机 + 录制
.venv/bin/dora build dataflow-ker.yaml --uv
.venv/bin/dora run dataflow-ker.yaml --uv
```

Leader：`dora-openarm-ker` → `nodes/dora-openarm-ker/src/dora_openarm_ker/main.py`

---

## 真机 · J6/J7 交换（KER J6→从臂 J7，KER J7→从臂 J6）

```bash
.venv/bin/dora build dataflow-ker-bimanual-j67-swap.yaml --uv
.venv/bin/dora run dataflow-ker-bimanual-j67-swap.yaml --uv
```

Leader：`dora-openarm-ker-j67-swap` → `nodes/dora-openarm-ker/src/dora_openarm_ker/main_j67_swap.py`

Follower config：`openarm_cell_j67_swap.yaml`（左夹爪限位 -1.25~0.05 rad，适配 swap 映射）

---

## Follower 配置文件

| 文件 | 用途 |
|------|------|
| `openarm_driver/.../openarm_cell.yaml` | 原版 leader（默认，左夹爪 -0.4~1.047 rad） |
| `openarm_driver/.../openarm_cell_j67_swap.yaml` | J6/J7 swap leader（j67 dataflow 通过 `--config` 指定） |

---

## dataflow 对照

| 文件 | 模式 |
|------|------|
| `dataflow-ker-mujoco.yaml` | 仿真 |
| `dataflow-ker-bimanual.yaml` | 真机双臂（原版） |
| `dataflow-ker.yaml` | 真机双臂 + 相机 + 录制（原版） |
| `dataflow-ker-bimanual-j67-swap.yaml` | 真机双臂（J6/J7 交换） |
