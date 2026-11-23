# KER 遥操作与数据采集

在仓库根目录操作：

```bash
cd /home/cereboto/worktest/dora-openarm-data-collection
```

## 启动前

真机需要 KER 主臂的 USB，以及从臂 CAN。先把 CAN 配好：

```bash
openarm-can-cli can_configure
```

每个 dataflow 都是两条命令。把 `<文件>` 换成下面某一节的 yaml：

```bash
.venv/bin/dora build <文件> --uv
.venv/bin/dora run <文件> --uv
```

`build` 会按 yaml 安装节点。依赖没变时，下次可以直接 `run`。结束时在该终端按 Ctrl+C。

浏览器打开 http://127.0.0.1:8000 。

| 按钮 | 作用 |
|------|------|
| Start Arm | 左右从臂都是 stopped 时出现。按下后从臂上电并对齐主臂。 |
| Pause Arm | 从臂已启动时出现。按下后从臂停止跟随。 |
| Start! | 开始一条 episode。页面变为 Collecting。 |
| Success! | 把当前 episode 标为成功并写入磁盘。 |
| Fail! | 把当前 episode 标为失败并写入磁盘。 |
| Cancel! | 丢掉当前 episode，不保留。 |

没有 recorder 的 dataflow 里，Start! / Success! / Fail! / Cancel! 仍会显示，但没有节点接收录制命令，不会产生数据集。

## 文件对照

| 文件 | 机械臂 | 遥操作 | 数据采集 | 相机 |
|------|--------|--------|----------|------|
| `dataflow-ker-bimanual-j67-swap.yaml` | 1.0 | 有 | 无 | 无 |
| `dataflow-j67-swap-record-nocameras.yaml` | 1.0 | 有 | 有 | 无 |
| `dataflow-ker-j67-swap-record.yaml` | 1.0 | 有 | 有 | 有 |
| `dataflow-ker-bimanual.yaml` | 2.0 | 有 | 无 | 无 |
| `dataflow-ker-bimanual-hand.yaml` | 右手为 Aero Hand | 有 | 无 | 无 |
| `dataflow-ker-joycon-all.yaml` | 2.0 | 有（Joy-Con） | 无 | 无 | 底盘 + 升降 |
| `dataflow-ker-joycon-all-rerun.yaml` | 2.0 | 有（Joy-Con） | 无 | 有 | Rerun 可视化 |
| `dataflow-ker-bimanual-rerun.yaml` | 2.0 | 有 | 无 | 有 | Rerun 可视化 |

1.0 的三个文件使用 `dora-openarm-ker-j67-swap`（`nodes/dora-openarm-ker/src/dora_openarm_ker/main_j67_swap.py`）：KER 的 J6 接到从臂 J7，KER 的 J7 接到从臂 J6。从臂配置是 `openarm_cell_j67_swap.yaml`，左夹爪额外带 `--align-gripper-above -0.35`。

2.0 和 Aero Hand 使用 `dora-openarm-ker`（`nodes/dora-openarm-ker/src/dora_openarm_ker/main.py`），关节一一对应。

## 1.0 遥操作，不录数据

`dataflow-ker-bimanual-j67-swap.yaml` 只跑 UI、主臂和左右从臂。

```bash
.venv/bin/dora build dataflow-ker-bimanual-j67-swap.yaml --uv
.venv/bin/dora run dataflow-ker-bimanual-j67-swap.yaml --uv
```

1. 打开 http://127.0.0.1:8000 ，确认左右状态都是 stopped。
2. 按 **Start Arm**。从臂对齐后即可用 KER 带动 1.0 双臂。
3. 停止跟随按 **Pause Arm**。退出整个程序在终端按 Ctrl+C。

## 1.0 数据采集，无相机

`dataflow-j67-swap-record-nocameras.yaml` 在上一节的双臂之外增加 recorder。不启动相机。数据集写到仓库下的 `j67_swap_record/dataset/`。

```bash
.venv/bin/dora build dataflow-j67-swap-record-nocameras.yaml --uv
.venv/bin/dora run dataflow-j67-swap-record-nocameras.yaml --uv
```

1. 打开 http://127.0.0.1:8000 ，按 **Start Arm**，等从臂对齐。
2. 按 **Start!**，页面变为 Collecting。此时记录左右臂的 action 和 observation，以及 KER metadata。
3. 这一条做完后选一个结果：
   - **Success!**：成功，写入 `j67_swap_record/dataset/episodes/<编号>/`
   - **Fail!**：失败，同样写入，并标为失败
   - **Cancel!**：这一条不保存
4. 可以再次 **Start!** 录下一条。全部结束后 Ctrl+C。

## 1.0 数据采集，带相机

`dataflow-ker-j67-swap-record.yaml` 同样是 1.0 的 J6/J7 交换遥操作，并且带 recorder。它会打开这四路相机，录制时把画面一起写入：

| 节点 | 设备 | 画面 |
|------|------|------|
| `camera-wrist-right` | `/dev/camera_wrist_right` | 右腕，960×600 |
| `camera-wrist-left` | `/dev/camera_wrist_left` | 左腕，960×600 |
| `camera-head-stereo` | `/dev/camera_head_stereo` | 头部双目并排，2560×720，再切成左右 |
| `camera-ceiling` | `/dev/camera_ceiling` | 顶视，960×600 |

yaml 里没有设置 `DIRECTORY`，数据集写到启动命令时所在目录下的 `dataset/`。在仓库根目录启动时，就是仓库里的 `dataset/`。

```bash
.venv/bin/dora build dataflow-ker-j67-swap-record.yaml --uv
.venv/bin/dora run dataflow-ker-j67-swap-record.yaml --uv
```

1. 确认四个设备节点存在，名称与上表一致。
2. 打开 http://127.0.0.1:8000 。页面下方 Camera streams 应出现 wrist R、wrist L、head L、head R、ceiling 的帧率。某一路一直是 `-- Hz`，先查对应的 `/dev/camera_*`。
3. 按 **Start Arm**，等从臂对齐。
4. 按 **Start!** 开始录。这一条里包含左右臂、KER metadata，以及五路图像（头部左右分开存）。
5. 用 **Success!**、**Fail!** 或 **Cancel!** 结束这一条。
6. 结果在 `dataset/episodes/<编号>/`。Ctrl+C 退出。

## 2.0 遥操作，不录数据

`dataflow-ker-bimanual.yaml` 只跑 UI、主臂和左右从臂，关节不交换，没有相机，也没有 recorder。

```bash
.venv/bin/dora build dataflow-ker-bimanual.yaml --uv
.venv/bin/dora run dataflow-ker-bimanual.yaml --uv
```

1. 打开 http://127.0.0.1:8000 。
2. 按 **Start Arm**。对齐后 KER 直接带动 2.0 双臂和夹爪。
3. **Pause Arm** 停止跟随，Ctrl+C 退出。

## 右手 Aero Hand 遥操作，不录数据

`dataflow-ker-bimanual-hand.yaml` 没有相机，也没有 recorder。右臂第 8 路不再当夹爪电机，改为 Aero Hand。左臂仍是夹爪。

右从臂参数是 `--drop-gripper --config openarm_cell_right_no_gripper.yaml`。Aero Hand 节点读取主臂右扳机：松开张开，按下握拢。右扳机仍然负责右臂对齐，手的开合不需要等对齐完成。

```bash
.venv/bin/dora build dataflow-ker-bimanual-hand.yaml --uv
.venv/bin/dora run dataflow-ker-bimanual-hand.yaml --uv
```

1. 接上 Aero Hand 的串口。节点默认自动寻找端口。
2. 打开 http://127.0.0.1:8000 ，按 **Start Arm**。
3. 用 KER 带动双臂。右手开合看右扳机，左手仍是夹爪。
4. **Pause Arm** 停止从臂跟随，Ctrl+C 退出。

## Joy-Con 全功能遥操作（底盘 + 升降，无相机）

`dataflow-ker-joycon-all.yaml` 在 2.0 双臂遥操作基础上加入 Joy-Con 映射、移动底盘和升降机构。

- 右臂对应 KER 通道 1-7，左臂对应通道 8-14。
- `ZR` 闭合右夹爪，`ZL` 闭合左夹爪。
- 右 Joy-Con 的 `B` 键停止整个 dataflow，等效于终端 Ctrl+C。
- 左摇杆控制底盘转向，右摇杆控制底盘前后移动。
- 左十字键控制升降上下。

```bash
.venv/bin/dora build dataflow-ker-joycon-all.yaml --uv
.venv/bin/dora run dataflow-ker-joycon-all.yaml --uv
```

1. 打开 http://127.0.0.1:8000 ，按 **Start Arm** 让从臂对齐。
2. 用 Joy-Con 带动双臂、底盘和升降。
3. **Pause Arm** 停止从臂，Ctrl+C 退出。

## Joy-Con 全功能遥操作 + Rerun（相机）

`dataflow-ker-joycon-all-rerun.yaml` 与 `dataflow-ker-joycon-all.yaml` 遥操作逻辑相同，但增加三路相机（右腕、左腕、头部双目）与 Rerun 可视化窗口，显示从臂实测关节位置与图像流。不录制数据集。

```bash
.venv/bin/dora build dataflow-ker-joycon-all-rerun.yaml --uv
.venv/bin/dora run dataflow-ker-joycon-all-rerun.yaml --uv
```

1. 确认 `/dev/camera_wrist_right`、`/dev/camera_wrist_left`、`/dev/camera_head_stereo` 设备存在。
2. 页面 Camera streams 应出现 wrist R、wrist L、head L、head R 帧率。
3. 按 **Start Arm** 后可用 Joy-Con 控制双臂、底盘和升降，Rerun 窗口同步显示。
4. **Pause Arm** 停止从臂，Ctrl+C 退出。

## 2.0 双臂遥操作 + Rerun（无底盘 / 升降）

`dataflow-ker-bimanual-rerun.yaml` 是 2.0 双臂遥操作的相机与 Rerun 可视化版本。它包含左右腕相机和头部双目相机，在 Rerun 中显示双臂关节位置与图像流，不含 Joy-Con、底盘和升降。

```bash
.venv/bin/dora build dataflow-ker-bimanual-rerun.yaml --uv
.venv/bin/dora run dataflow-ker-bimanual-rerun.yaml --uv
```

1. 打开 http://127.0.0.1:8000 。
2. 按 **Start Arm**，对齐后用 KER 带动 2.0 双臂。
3. Rerun 窗口显示双臂关节位置与相机画面。
4. **Pause Arm** 停止，Ctrl+C 退出。
