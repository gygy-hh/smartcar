# Jetson 调用 TC377 底盘串口 API

这个目录给 Jetson 上位机使用，通过串口调用 TC377 下位机的底盘控制命令。当前已经封装底盘移动、单轮速度、编码器读取、PI/FF 参数设置等函数。

底层协议是 TC377 固件已有的 ASCII 串口命令，例如：

```text
XYW 30 0 0
VSTOP
ENC?
PID 1 120 5
FF 1 0 80
```

Python 文件会负责发送命令、等待 `OK ...` 响应、解析 `ENC?` 编码器返回，并在下位机返回 `ERR ...` 或超时时抛异常。

## 文件结构

```text
jetson_tc377/
  __init__.py
  tc377_chassis_api.py
  README.md
```

核心类：

```python
from jetson_tc377 import TC377Chassis
```

## 1. 创建 Python 虚拟环境

在 Jetson 上进入工程目录：

```bash
cd /path/to/baidu-smartcar
```

创建并进入虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

安装依赖：

```bash
python -m pip install --upgrade pip
python -m pip install pyserial
```

如果 `python3 -m venv .venv` 报错，先安装 venv：

```bash
sudo apt update
sudo apt install python3-venv
```

退出虚拟环境：

```bash
deactivate
```

## 2. 查看 TC377 串口

### 方法 A：列出常见串口

```bash
ls /dev/ttyUSB* /dev/ttyACM* /dev/ttyTHS* /dev/ttyS* 2>/dev/null
```

常见结果：

```text
/dev/ttyUSB0
/dev/ttyACM0
/dev/ttyTHS1
```

一般 USB 转串口是 `/dev/ttyUSB0`，USB CDC 设备可能是 `/dev/ttyACM0`，Jetson 板载串口可能是 `/dev/ttyTHS1`。

### 方法 B：插拔对比

先插上 TC377 串口线：

```bash
ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
```

拔掉线再执行一次。少掉的那个设备就是 TC377 对应串口。

### 方法 C：看内核日志

插上线后执行：

```bash
dmesg | tail -50
```

如果看到类似 `ttyUSB0`、`ttyACM0`，就用对应路径作为 `port`。

### 串口权限

查看权限：

```bash
ls -l /dev/ttyUSB0
```

临时测试可以：

```bash
sudo chmod 666 /dev/ttyUSB0
```

长期建议把当前用户加入 `dialout` 组：

```bash
sudo usermod -aG dialout $USER
```

然后重新登录 Jetson。

## 3. 快速跑通

确认 TC377 已经烧录支持 `XYW`、`VSTOP`、`ENC?` 的固件，车轮先悬空。

假设串口是 `/dev/ttyUSB0`，先跑一个很小的前进速度：

```bash
source .venv/bin/activate
python jetson_tc377/tc377_chassis_api.py --port /dev/ttyUSB0 --x 0.05 --duration 0.5
```

这条命令会：

1. 打开 `/dev/ttyUSB0`
2. 发送底盘速度
3. 运行 `0.5s`
4. 自动发送 `VSTOP`
5. 读取并打印 `ENC?` 编码器数据

如果能看到类似输出，说明上位机和下位机串口已通：

```text
{1: EncoderSample(motor=1, position=..., velocity=...), ...}
```

## 4. 最小业务代码

新建一个测试脚本，例如 `test_chassis.py`：

```python
from jetson_tc377 import TC377Chassis

PORT = "/dev/ttyUSB0"

with TC377Chassis(PORT, ticks_per_meter=7800.0) as car:
    car.set_velocity(0.10, 0.0, 0.0)   # 前进，单位 m/s
    car.delay(0.5)
    car.stop()

    encoders = car.get_encoders()
    for motor, sample in sorted(encoders.items()):
        print(motor, sample.position, sample.velocity)
```

运行：

```bash
python test_chassis.py
```

## 5. 坐标约定

`TC377Chassis.set_velocity(x, y, z)` 按 `docs/api.md` 的习惯：

```text
x > 0：前进，单位 m/s
y > 0：向左平移，单位 m/s
z > 0：逆时针旋转，单位 rad/s
```

TC377 固件的原始 `XYW` 命令约定是：

```text
x > 0：前进
y > 0：向右平移
w > 0：顺时针旋转
```

所以 Python 封装在 `set_velocity()` 里会自动把 `y` 和 `z` 取反后发给固件。

举例，假设 `ticks_per_meter=1000`：

```python
car.set_velocity(0.20, 0.10, 0.50)
```

会转换成类似：

```text
XYW 10 -5 -25
```

## 6. 先测方向

刚接车时，建议先用原始单位 `set_xyw_raw()` 小速度测方向。车轮悬空，速度不要太大。

```python
from jetson_tc377 import TC377Chassis

with TC377Chassis("/dev/ttyUSB0") as car:
    print(car.set_xyw_raw(30, 0, 0))       # 固件前进
    car.delay(0.5)
    print(car.stop())

    print(car.set_xyw_raw(0, 30, 0))       # 固件右移
    car.delay(0.5)
    print(car.stop())

    print(car.set_xyw_raw(0, 0, 1000))     # 固件顺时针
    car.delay(0.5)
    print(car.stop())
```

如果方向正确，再使用 `set_velocity()` 的 m/s、rad/s 接口。

## 7. API 总览

### `TC377Chassis(port, baudrate=115200, timeout=0.05, command_timeout=0.50, ticks_per_meter=7800.0)`

打开串口并创建底盘对象。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `port` | str | 串口路径，例如 `/dev/ttyUSB0` |
| `baudrate` | int | 波特率，默认 `115200` |
| `timeout` | float | 串口单次读超时 |
| `command_timeout` | float | 等待一条命令响应的总超时 |
| `ticks_per_meter` | float | m/s 转换到 ticks/50ms 的标定参数 |

推荐使用 `with`，退出时会自动 `stop()` 并关闭串口：

```python
with TC377Chassis("/dev/ttyUSB0") as car:
    car.stop()
```

### `set_velocity(x, y, z) -> str`

设置底盘速度，接口仿照 `docs/api.md`。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `x` | float | 前后速度，单位 m/s，正数前进 |
| `y` | float | 左右速度，单位 m/s，正数左移 |
| `z` | float | 旋转角速度，单位 rad/s，正数逆时针 |

返回 TC377 的 `OK XYW ...` 字符串。

```python
car.set_velocity(0.10, 0.0, 0.0)    # 前进
car.set_velocity(0.0, 0.10, 0.0)    # 左移
car.set_velocity(0.0, 0.0, 0.50)    # 逆时针
```

### `set_velocity_for_duration(x, y, z, duration=1.0) -> None`

按指定速度运行一段时间，然后自动 `stop()`。

```python
car.set_velocity_for_duration(0.10, 0.0, 0.0, duration=1.0)
```

### `move_time(sp, dur_time=1.0, stop=None) -> None`

仿照官方车 API，按 `[x, y, z]` 速度运行指定时间。

```python
car.move_time([0.10, 0.0, 0.0], dur_time=1.0)
```

`stop=None` 时使用类变量 `STOP_PARAM`，默认结束后停车。

### `move_base(sp, end_function, stop=None, poll_interval=0.02) -> None`

持续移动，直到 `end_function()` 返回 `True`。

```python
car.move_base([0.10, 0.0, 0.0], lambda: sensor_triggered())
```

### `move_distance(sp, dis=0.1, stop=None) -> None`

按速度和时间估算移动距离。当前没有上位机里程计闭环，只适合粗略动作。

```python
car.move_distance([0.10, 0.0, 0.0], dis=0.30)
```

### `delay(time_hold) -> None`

等待指定秒数。

```python
car.delay(0.5)
```

### `stop() -> str`

发送 `VSTOP`，停止闭环底盘运动。

```python
print(car.stop())
```

### `brake() -> str`

发送 `BRAKE`，主动刹车。

```python
print(car.brake())
```

### `set_xyw_raw(x_ticks, y_right_ticks, w_clockwise_raw) -> str`

直接发送固件原始 `XYW` 单位。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `x_ticks` | int | 前进方向目标，单位 ticks/50ms |
| `y_right_ticks` | int | 右移方向目标，单位 ticks/50ms |
| `w_clockwise_raw` | int | 顺时针旋转原始量 |

```python
car.set_xyw_raw(30, 0, 0)
car.set_xyw_raw(0, 30, 0)
car.set_xyw_raw(0, 0, 1000)
```

### `set_wheel_speed(motor, ticks_per_period) -> str`

设置单个轮子的闭环速度，对应下位机 `V1` 到 `V4`。

```python
car.set_wheel_speed(1, 80)
```

### `set_all_wheel_speed(ticks_per_period) -> str`

四个轮子设置相同闭环速度，对应下位机 `VALL`。

```python
car.set_all_wheel_speed(60)
```

### `get_encoders() -> dict[int, EncoderSample]`

读取四个电机的编码器位置和速度。

```python
enc = car.get_encoders()
print(enc[1].position, enc[1].velocity)
```

返回：

```text
{
  1: EncoderSample(motor=1, position=..., velocity=...),
  2: EncoderSample(motor=2, position=..., velocity=...),
  3: EncoderSample(motor=3, position=..., velocity=...),
  4: EncoderSample(motor=4, position=..., velocity=...),
}
```

其中：

| 字段 | 说明 |
| --- | --- |
| `motor` | 电机编号，1 到 4 |
| `position` | 累计脉冲位置 |
| `velocity` | 当前速度，单位 ticks/50ms |

### `get_encoder(motor) -> EncoderSample`

读取单个电机编码器。

```python
m1 = car.get_encoder(1)
print(m1.position, m1.velocity)
```

### `reset_pid() -> str`

清除 PI 积分状态。

```python
print(car.reset_pid())
```

### `set_pid(motor, kp, ki) -> str`

设置单个电机 PI 参数。当前下位机 `SCALE=100`：

```text
kp = 100 表示 Kp=1.00
ki = 5   表示 Ki=0.05
```

示例：

```python
car.set_pid(1, 100, 5)
```

### `set_feedforward(motor, dead, gain) -> str`

设置单个电机前馈增益。当前 `gain` 也是 `SCALE=100`：

```text
gain = 80 表示 FF_GAIN=0.80
```

`dead` 字段仅为兼容下位机旧命令格式，当前固件会忽略它并返回 `DEAD=0`。

```python
car.set_feedforward(1, 0, 80)
```

## 8. 麦轮布局

TC377 下位机当前电机布局：

```text
V1 = 左前
V2 = 左后
V3 = 右后
V4 = 右前
```

下位机 `XYW` 解算：

```text
rot = (L + W) * w / 1000
V1 = x + y + rot
V2 = x - y + rot
V3 = x + y - rot
V4 = x - y - rot
```

底盘参数：

```text
L = 105 mm
W = 123.32248601 mm
```

## 9. 异常处理

常见异常：

| 异常 | 触发原因 |
| --- | --- |
| `TC377Error` | 基础异常，所有 TC377 API 异常的父类 |
| `TC377CommandError` | 下位机返回 `ERR CMD`、`ERR RANGE`、`ERR FLASH` |
| `TC377TimeoutError` | 超时没有等到期望响应 |
| `ValueError` | Python 侧参数越界，例如电机号不是 1 到 4 |

示例：

```python
from jetson_tc377 import TC377Chassis, TC377Error

try:
    with TC377Chassis("/dev/ttyUSB0") as car:
        car.set_velocity_for_duration(0.10, 0.0, 0.0, 0.5)
except TC377Error as exc:
    print("TC377 communication failed:", exc)
```

## 10. 常见问题

### 找不到 `/dev/ttyUSB0`

先执行：

```bash
ls /dev/ttyUSB* /dev/ttyACM* /dev/ttyTHS* /dev/ttyS* 2>/dev/null
dmesg | tail -50
```

如果插拔后没有新增设备，检查 USB 线、串口模块供电、TC377 是否上电。

### `Permission denied`

临时：

```bash
sudo chmod 666 /dev/ttyUSB0
```

长期：

```bash
sudo usermod -aG dialout $USER
```

然后重新登录。

### `TC377TimeoutError`

可能原因：

- 串口选错了
- 波特率不是 `115200`
- TC377 没有运行新版固件
- 下位机串口线 TX/RX 没接对
- TC377 正在复位或卡在初始化

先用串口助手手动发：

```text
ENC?
```

如果没有返回 `ENC M1 ...`，先排查下位机和串口线。

### `TC377CommandError: ERR CMD`

说明下位机收到了命令，但固件不认识。常见原因是 TC377 还没烧录包含 `XYW` 命令的新固件。

### 车不动但串口返回 OK

按顺序查：

1. 轮子是否悬空测试过
2. TC377 电机电源是否打开
3. `ENC?` 的 `vel` 是否变化
4. PI/FF 参数是否太小
5. 下位机 `VSTOP` 后再重新发小速度

### 方向不对

先用 `set_xyw_raw()` 测固件原始方向，再决定是改上位机调用方向，还是改 TC377 固件里的电机方向宏。

## 11. 推荐给队友的最短接入模板

```python
from jetson_tc377 import TC377Chassis, TC377Error

PORT = "/dev/ttyUSB0"

def main():
    with TC377Chassis(PORT, ticks_per_meter=7800.0) as car:
        car.reset_pid()
        car.set_feedforward(1, 0, 80)
        car.set_pid(1, 100, 5)

        car.move_time([0.10, 0.0, 0.0], dur_time=0.5)
        car.move_time([0.0, 0.10, 0.0], dur_time=0.5)
        car.move_time([0.0, 0.0, 0.50], dur_time=0.5)

        print(car.get_encoders())
        car.stop()

if __name__ == "__main__":
    try:
        main()
    except TC377Error as exc:
        print(exc)
```
