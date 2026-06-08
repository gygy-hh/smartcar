# car_wrap_2026.py 接口文档
> 本文档针对**全国智能车比赛百度创意组鲸鱼机器人**提供的官方案例车封装进行说明。大家也可以参考这个文档自己封装一辆车。
>
> 创建实例时自动初始化所有硬件、加载配置并启动按键检测线程。程序结束时调用 `close()` 释放资源。
>

---

## 目录
+ [1. 底盘移动](#1-底盘移动)
+ [2. 车道保持](#2-车道保持)
+ [3. 目标检测与定位](#3-目标检测与定位)
+ [4. 机械臂](#4-机械臂)
+ [5. 传感器](#5-传感器)
+ [6. 摄像头](#6-摄像头)
+ [7. 视觉感知与识别](#7-视觉感知与识别)
+ [8. 调试与程序管理](#8-调试与程序管理)

---

## 1. 底盘移动
> 速度参数 `[x, y, z]`：x 为前进/后退 (m/s)，y 为左右平移 (m/s)，z 为转向角速度 (rad/s，逆时针为正)。
>

### `set_velocity(x, y, z)`
设置底盘实时速度。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `x` | float | 前后方向速度，正=前进 |
| `y` | float | 左右方向速度，正=向左平移 |
| `z` | float | 转向角速度，正=逆时针 |


---

### `stop()`
立即停止底盘运动，速度置零。

---

### `set_velocity_for_duration(x, y, z, duration=1.0)`
以指定速度行驶一段时间。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `x, y, z` | float | 同 `set_velocity` |
| `duration` | float | 持续时间（秒），默认 1.0 |


---

### `get_odometry(show_info=False) -> np.ndarray`
获取当前里程计位置 `[x, y, theta]`。

---

### `get_distance(show_info=False) -> float`
获取车辆累计行驶距离。

---

### `reset_position(x=0, y=0, z=0.0)`
重置里程计坐标到指定位置（默认原点）。

---

### `move_for(position_offset, duration=None, max_velocities=None, tolerance=None)`
移动到绝对位置（基于当前里程计的偏移量）。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `position_offset` | tuple/list | 目标位置偏移 `[dx, dy, dtheta]` |
| `duration` | float | 运动持续时间（秒），None=自动 |
| `max_velocities` | tuple | `[vx_max, vy_max, omega_max]` |
| `tolerance` | tuple | `[x_tol, y_tol, theta_tol]` 容差 |


---

### `move_to_position(target_position, duration=None, max_velocities=(0.2, 0.2, pi/3), tolerance=(0.004, 0.004, 0.02), timeout=30.0)`
移动到指定绝对坐标（世界坐标系），使用 PID 控制。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `target_position` | tuple/list | 目标位置 `[x, y, theta]` |
| `timeout` | float | 超时时间（秒） |


---

### `move_base(sp, end_fuction, stop=STOP_PARAM)`
按给定速度移动，直到 `end_fuction` 返回 True。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `sp` | list | 速度向量 `[x, y, z]` |
| `end_fuction` | callable | 结束条件回调，无参数返回 bool |
| `stop` | bool | 到达后是否停止，默认 True |


---

### `move_time(sp, dur_time=1, stop=STOP_PARAM)`
按时间移动。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `sp` | list | 速度向量 `[x, y, z]` |
| `dur_time` | float | 移动时间（秒），默认 1.0 |
| `stop` | bool | 到达后是否停止，默认 True |


---

### `move_distance(sp, dis=0.1, stop=STOP_PARAM)`
按距离移动。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `sp` | list | 速度向量 `[x, y, z]` |
| `dis` | float | 移动距离（米），默认 0.1 |
| `stop` | bool | 到达后是否停止，默认 True |


---

### `move_advance(sp, value_h=1200, value_l=0, times=1, sides=1, dis_out=0.2, stop=STOP_PARAM)`
按红外传感器条件移动，直到传感器读数进入 `[value_l, value_h]` 区间。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `sp` | list | 速度向量 `[x, y, z]` |
| `value_h` | int | 传感器上限，默认 1200 |
| `value_l` | int | 传感器下限，默认 0 |
| `times` | int | 重复次数，默认 1 |
| `sides` | int | 1=左侧传感器，-1=右侧传感器 |
| `dis_out` | float | 移动距离限制（米），默认 0.2 |
| `stop` | bool | 到达后是否停止，默认 True |


---

### `delay(time_hold)`
延时等待，期间响应停止标志。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `time_hold` | float | 延时时间（秒） |


---

### `STOP_PARAM` 类变量
控制 `move_*` 系列方法的默认 `stop` 行为。设为 `False` 后，移动方法结束后不会自动停车。

```python
my_car.STOP_PARAM = False  # 移动后不自动停车
```

---

## 2. 车道保持
> 使用前置摄像头 (`cap_front`) 进行车道线检测，通过内置 PID 控制器自动调整方向，保持车辆在车道中间行驶。
>

### `lane_base(speed, end_fuction, stop=STOP_PARAM)`
车道保持基础方法，持续进行车道线检测直到满足结束条件。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `speed` | float | 前进速度 (m/s)，正=前进 |
| `end_fuction` | callable | 结束条件回调，无参数返回 bool |
| `stop` | bool | 到达后是否停止，默认 True |


---

### `lane_time(speed, time_dur, stop=STOP_PARAM)`
车道保持定时行驶。

---

### `lane_dis(speed, dis_end, stop=STOP_PARAM)`
车道保持定距行驶，累计行驶距离超过 `dis_end` 时停止。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `speed` | float | 前进速度 (m/s) |
| `dis_end` | float | 累计行驶距离（米） |
| `stop` | bool | 到达后是否停止，默认 True |


---

### `lane_dis_offset(speed, dis_hold, stop=STOP_PARAM)`
车道保持相对距离行驶，从当前位置再行驶 `dis_hold` 米后停止。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `speed` | float | 前进速度 (m/s) |
| `dis_hold` | float | 从当前位置再行驶的距离（米） |
| `stop` | bool | 到达后是否停止，默认 True |


---

### `lane_sensor(speed, value_h=1200, value_l=0, dis_offset=0.0, times=1, sides=1, stop=STOP_PARAM)`
车道保持 + 红外传感器触发，传感器读数进入区间后停止，可额外行驶一段距离。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `speed` | float | 前进速度 (m/s) |
| `value_h` | int | 传感器上限，默认 1200 |
| `value_l` | int | 传感器下限，默认 0 |
| `dis_offset` | float | 到达后额外行驶距离，默认 0 |
| `times` | int | 重复次数，默认 1 |
| `sides` | int | 1=左侧传感器，-1=右侧传感器 |
| `stop` | bool | 到达后是否停止，默认 True |


---

### `walk_lane_test()`
车道行走测试，以 0.3 m/s 速度无限直行（配合 `stop()` 或按键3终止）。

---

## 3. 目标检测与定位
> 使用前置摄像头 (`cap_front`) 检测前方目标，或侧面摄像头 (`cap_side`) 定位任务目标，配合内置 PID 实现"追着目标走"。
>

### `lane_det_base(speed, end_fuction, stop=STOP_PARAM)`
目标检测基础方法，使用前置摄像头检测目标并自动调整方向。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `speed` | float | 前进速度 (m/s) |
| `end_fuction` | callable | 结束条件回调，接收距离参数 `d` 返回 bool |
| `stop` | bool | 到达后是否停止，默认 True |


```python
# 示例：当距离 < 0.16m 时停止
end_fuction = lambda d: d < 0.16 and d != 0
```

---

### `lane_det_time(speed, time_dur, stop=STOP_PARAM)`
目标检测定时行驶，持续 `time_dur` 秒。

---

### `lane_det_dis2pt(speed, dis_end, stop=STOP_PARAM)`
目标检测定距行驶，当与目标距离小于 `dis_end` 时停止。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `speed` | float | 前进速度 (m/s) |
| `dis_end` | float | 目标距离阈值（米） |
| `stop` | bool | 到达后是否停止，默认 True |


---

### `lane_det_location(speed, pts_tar, dis_out=0.05, side=1, time_out=2, det='task') -> int | False`
使用**侧面摄像头**定位目标，移动车辆使目标处于指定相对位置。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `speed` | float | 移动速度 (m/s) |
| `pts_tar` | list | 目标列表，格式：`[id, 宽度(mm), 标签, 置信度, x_c, y_c, w, h]` |
| `dis_out` | float | 移动距离限制（米），默认 0.05 |
| `side` | int | 方向，1=正方向，-1=反方向 |
| `time_out` | float | 超时时间（秒），默认 2 |
| `det` | str | 检测类型，默认 'task' |


返回：目标索引（成功）或 `False`（超时/超距）

```python
dets = [[15, 60, "cylinder3", 0, 0, 0, 0.47, 0.7],
        [14, 80, "cylinder2", 0, 0, 0, 0.69, 0.7]]
my_car.lane_det_location(0.2, dets)
```

---

### `det2pose(det, w_r=0.06) -> tuple`
将检测框转换为真实世界坐标。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `det` | list | 检测结果 `[x_c, y_c, w, h]`，归一化坐标 |
| `w_r` | float | 物体实际宽度（米），默认 0.06 |


返回：`(x, y, distance)` — 目标相对小车的 x、y 坐标和距离（米）

---

### `get_card_side() -> int`
检测卡片左右指示，返回 `-1`=右转，`1`=左转，`0`=未检测到。

---

### `get_detection_results() -> List[list]`
获取侧面摄像头的目标检测结果，按距离由近及远排序。

返回：每个元素为 `[cls_id, obj_id, label, score, x_c, y_c, w, h]`

---

### `get_target_location(det) -> tuple`
根据检测结果计算目标相对小车的真实世界坐标（考虑机械臂位置）。

返回：`(loc_x, loc_y)` — 目标在小车坐标系下的坐标

---

### `move_to_detection_target(delta_x=0.0, delta_y=0.0, cls_id=None, time_out=2.0)`
前往并对齐到检测目标位置，自动调整底盘和机械臂。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `delta_x` | float | 目标相对小车的 x 偏移（米） |
| `delta_y` | float | 目标相对小车的 y 偏移（米） |
| `cls_id` | int | 指定目标类别，None=最近的任意目标 |
| `time_out` | float | 超时时间（秒），默认 2.0 |


返回：`(cls_id, label)` 或 `(-1, "None")`（超时）

---

### `adjust_arm_position()`
微调机械臂位置（根据朝向偏移 0.05m），用于目标对齐后的精细调整。

---

## 4. 机械臂
> 通过 `my_car.arm` 访问，控制垂直升降、水平伸缩、夹爪开合及角度姿态。
>

### 机械臂属性（直接访问）
| 属性 | 类型 | 说明 |
| --- | --- | --- |
| `arm.arm_length` | float | 机械臂长度（米） |
| `arm.x_pose_now` | float | 水平方向当前位置（米） |
| `arm.y_pose_now` | float | 垂直方向当前位置（米） |
| `arm.side` | str | 机械臂朝向，`"LEFT"` / `"RIGHT"` / `"MID"` |


---

### `arm.reset_position()`
完整复位机械臂（水平和垂直方向均复位）。

---

### `arm.reset_y()` / `arm.reset_x()`
垂直/水平方向单独复位。

---

### `arm.goto_position(x, y, time_run=None, speed=[0.15, 0.04])`
移动机械臂到绝对坐标位置。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `x` | float | 水平位置（米） |
| `y` | float | 垂直位置（米） |
| `time_run` | float | 运行时间（秒），None=根据速度自动计算 |
| `speed` | list | `[水平速度, 垂直速度]` |


---

### `arm.go_for(x_offset, y_offset, time_run=None, speed=[0.15, 0.04])`
相对移动机械臂（基于当前位姿的偏移量）。

---

### `arm.grasp(value: bool)`
控制夹爪，`True`=抓取，`False`=松开。

---

### `arm.set_arm_pose(x, y, arm=None, hand=None)`
设置机械臂完整姿态（位置 + 角度）。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `x` | float | 水平位置（米） |
| `y` | float | 垂直位置（米） |
| `arm` | str | 朝向 `"LEFT"`/`"MID"`/`"RIGHT"`，None=保持不变 |
| `hand` | str | 夹爪角度 `"UP"`/`"MID"`/`"DOWN"`，None=保持不变 |


---

### `arm.set_arm_angle(angle, speed=80)`
设置机械臂角度，参数可为字符串或角度数值。

---

### `arm.set_hand_angle(angle, speed=80)`
设置夹爪角度，参数可为字符串或角度数值。

---

### `arm.switch_side(side)`
切换机械臂朝向，参数为 `"LEFT"`、`"RIGHT"` 或 `"MID"`。

---

### `arm.x_speed(velocity)` / `arm.y_speed(velocity)`
设置水平/垂直方向实时速度，常用于持续跟踪场景。

---

### `arm.move_x_distance(target)`
移动水平方向到指定位置（米）。

---

### `arm.save_config(pose_enable=True)`
保存当前配置到 YAML 文件。

---

## 5. 传感器
### `beep()`
发出蜂鸣音一声，并等待 0.2 秒。

---

### `left_sensor.read() -> int` / `right_sensor.read() -> int`
读取左侧/右侧红外传感器值（灰度/反射值）。

---

### `key.get_key() -> int`
读取按键值：短按 `1`/`2`/`3`/`4`，长按 `5`/`6`/`7`/`8`，无按键返回 `0`。

---

### `light`
LED 灯控制器（`LedLight` 实例），可控制车灯状态。

---

### `display.show(text)`
在车身高亮屏上显示文字。

```python
my_car.display.show("Hello")
```

---

## 6. 摄像头
### `cap_front`
前置摄像头（`Camera` 实例）。用于车道线检测、前向目标检测和卡片识别。

```python
image = my_car.cap_front.read()      # 读取一帧图像
my_car.cap_front.isOpened()          # 判断摄像头是否正常打开
my_car.cap_front.close()             # 关闭摄像头
```

---

### `cap_side`
侧面摄像头（`Camera` 实例）。用于任务目标检测和 OCR 识别。

```python
image = my_car.cap_side.read()       # 读取一帧图像
my_car.cap_side.isOpened()           # 判断摄像头是否正常打开
my_car.cap_side.close()              # 关闭摄像头
```

---

### `streamer`
视频流处理器，将帧推送至前端页面查看。

```python
my_car.streamer.update_frame(image, "cam1")  # 推送前置画面
my_car.streamer.update_frame(image, "cam2")  # 推送侧面画面
my_car.streamer.stop()                        # 停止推送
```

---

## 7. 视觉感知与识别
### `get_ocr(time_out=3) -> str | None`
OCR 文字识别，使用侧面摄像头拍摄并识别图像中的文字。连续 3 次检测到相似度 >85% 的相同文本才返回稳定结果。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `time_out` | float | 超时时间（秒），默认 3 |


---

### 文心一言分析（需先调用 `ernie_bot_init()` 初始化）
> 以下功能需要先调用 `my_car.ernie_bot_init()` 初始化文心一言接口。
>

#### `yiyan_get_humattr(text) -> dict`
人类属性分析，根据文本描述分析人物外貌属性。

#### `yiyan_get_actions(text) -> dict`
动作分析，分析文本中描述的动作信息。

---

## 8. 调试与程序管理
### `debug()`
调试模式，实时显示车道线检测误差、侧面摄像头目标检测结果及距离、左右红外传感器值。常用于验证传感器和推理服务是否正常工作。

---

### `close()`
关闭智能车，释放所有资源（停止按键线程、关闭摄像头、停止流推送）。

---

### `manage(programs_list, order_index=0)`
程序管理菜单，通过车身上 4 个按键选择和执行不同程序。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `programs_list` | list | 要管理的函数列表 |
| `order_index` | int | 初始选中索引，默认 0 |


内置快捷程序：顺序执行所有程序（延时 4 秒后开始）、车道保持 30m、机械臂复位、调试模式。

**按键操作：** 按键2/4 上下选择，按键3 确定执行，按键1 长按退出。

```python
def start_det_loc():
    dets = [[15, 60, "cylinder3", 0, 0, 0, 0.47, 0.7]]
    my_car.lane_det_location(0.2, dets)

my_car.manage([start_det_loc])
```
