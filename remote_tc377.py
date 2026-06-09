#!/usr/bin/env python3
"""用手柄直连 Jetson 遥控 TC377 底盘。

本车手柄映射（BEITONG / Xbox 类）:
  右摇杆 axis 4=前进/后退, axis 3=左移/右移
  左摇杆=旋转(自动扫描除右摇杆/扳机外的所有轴)
  LT=axis 2, RT=axis 5
  A/B/X/Y=button 0/1/2/3, Back=6, Start=7

用法：
  python remote_tc377.py
  python remote_tc377.py --debug-sticks   # 实时看摇杆数值
  python remote_tc377.py --probe

退出：Back(button 6)、Ctrl+C，摇杆回中自动停车。
"""

from __future__ import annotations

import argparse
import glob
import os
import select
import struct
import sys
import time
from typing import Dict, List, Optional, Tuple

from jetson_tc377 import TC377Chassis, TC377Error

JS_EVENT_FORMAT = "IhBB"
JS_EVENT_SIZE = struct.calcsize(JS_EVENT_FORMAT)

JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_BUTTON_INIT = 0x81
JS_EVENT_AXIS_INIT = 0x82

DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_JS = "/dev/input/js0"
DEFAULT_MAX_LINEAR = 100
DEFAULT_MAX_ROTATE = 500
DEFAULT_MIN_LINEAR = 40
DEFAULT_DEADZONE = 0.08
DEFAULT_POLL_HZ = 25.0
DEFAULT_STATUS_INTERVAL = 2.0

# 右摇杆: axis 4=前进/后退, axis 3=左移/右移
# 旋转: 自动扫描除 DRIVE_AXES 外所有轴（左摇杆可能是 0/1 或 6/7）
DEFAULT_AXIS_FORWARD = 4
DEFAULT_AXIS_STRAFE = 3
DEFAULT_ROTATE_EXCLUDE = [2, 3, 4, 5]
DEFAULT_SIGN_FORWARD = -1.0
DEFAULT_SIGN_STRAFE = -1.0
DEFAULT_SIGN_ROTATE = -1.0
DEFAULT_EXIT_BUTTONS = [6]
DEFAULT_MIN_ROTATE = 100


class Joystick:
    """读取 Linux /dev/input/js* 设备。"""

    def __init__(self, path: str) -> None:
        self.path = path
        self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        self.axes: Dict[int, float] = {}
        self.buttons: Dict[int, bool] = {}
        self._drain_initial_events()

    def close(self) -> None:
        os.close(self.fd)

    def _drain_initial_events(self) -> None:
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            self.poll()

    def poll(self) -> None:
        while True:
            ready, _, _ = select.select([self.fd], [], [], 0)
            if not ready:
                break
            data = os.read(self.fd, JS_EVENT_SIZE)
            if len(data) != JS_EVENT_SIZE:
                break
            _time_ms, value, event_type, number = struct.unpack(JS_EVENT_FORMAT, data)
            if event_type in (JS_EVENT_AXIS, JS_EVENT_AXIS_INIT):
                self.axes[number] = normalize_axis(value)
            elif event_type in (JS_EVENT_BUTTON, JS_EVENT_BUTTON_INIT):
                self.buttons[number] = bool(value)

    def axis(self, number: int, default: float = 0.0) -> float:
        return self.axes.get(number, default)

    def any_button_pressed(self, numbers: List[int]) -> bool:
        return any(self.buttons.get(number, False) for number in numbers)


def normalize_axis(raw: int) -> float:
    return max(-1.0, min(1.0, raw / 32767.0))


def apply_deadzone(value: float, deadzone: float) -> float:
    if abs(value) < deadzone:
        return 0.0
    sign = 1.0 if value > 0 else -1.0
    scaled = (abs(value) - deadzone) / (1.0 - deadzone)
    return sign * min(1.0, scaled)


def apply_min_command(value: int, minimum: int) -> int:
    if value == 0:
        return 0
    if abs(value) < minimum:
        return minimum if value > 0 else -minimum
    return value


def find_js_device(preferred: str) -> Optional[str]:
    if os.path.exists(preferred):
        return preferred
    candidates = sorted(glob.glob("/dev/input/js*"))
    return candidates[0] if candidates else None


def read_rotate(joy: Joystick, args: argparse.Namespace) -> Tuple[float, int]:
    """自动扫描左摇杆轴作为旋转输入，排除右摇杆和扳机轴。"""
    exclude = set(args.rotate_exclude)
    best = 0.0
    best_axis = -1

    if args.rotate_axes:
        for axis in args.rotate_axes:
            value = apply_deadzone(joy.axis(axis) * args.sign_rotate, args.deadzone)
            if abs(value) > abs(best):
                best = value
                best_axis = axis
        return best, best_axis

    candidate_axes = set(joy.axes.keys())
    candidate_axes.update([0, 1, 6, 7])

    for axis in sorted(candidate_axes):
        if axis in exclude:
            continue
        raw = joy.axis(axis)
        value = apply_deadzone(raw * args.sign_rotate, args.deadzone)
        if abs(value) > abs(best):
            best = value
            best_axis = axis
    return best, best_axis


def sticks_to_xyw(joy: Joystick, args: argparse.Namespace) -> Tuple[int, int, int]:
    forward = apply_deadzone(
        joy.axis(args.axis_forward) * args.sign_forward,
        args.deadzone,
    )
    strafe = apply_deadzone(
        joy.axis(args.axis_strafe) * args.sign_strafe,
        args.deadzone,
    )
    rotate, _rotate_axis = read_rotate(joy, args)

    x_ticks = int(round(forward * args.max_linear))
    y_right_ticks = int(round(-strafe * args.max_linear))
    w_raw = int(round(-rotate * args.max_rotate))

    if args.min_linear > 0:
        x_ticks = apply_min_command(x_ticks, args.min_linear)
        y_right_ticks = apply_min_command(y_right_ticks, args.min_linear)
    if args.min_rotate > 0:
        w_raw = apply_min_command(w_raw, args.min_rotate)

    return x_ticks, y_right_ticks, w_raw


def format_active_axes(joy: Joystick, exclude: set[int]) -> str:
    parts = []
    candidate_axes = set(joy.axes.keys())
    candidate_axes.update([0, 1, 6, 7])
    for axis in sorted(candidate_axes):
        if axis in exclude:
            continue
        value = joy.axis(axis)
        if abs(value) > 0.05:
            parts.append(f"a{axis}={value:+.2f}")
    return " ".join(parts) if parts else "none"


def format_stick_debug(joy: Joystick, args: argparse.Namespace) -> str:
    fwd = joy.axis(args.axis_forward) * args.sign_forward
    stf = joy.axis(args.axis_strafe) * args.sign_strafe
    rot, rot_axis = read_rotate(joy, args)
    exclude = set(args.rotate_exclude)
    active = format_active_axes(joy, exclude)
    return (
        f"fwd(a{args.axis_forward})={fwd:+.2f} "
        f"str(a{args.axis_strafe})={stf:+.2f} "
        f"rot={rot:+.2f}(a{rot_axis}) [{active}]"
    )


def run_probe(js_path: str, seconds: float = 10.0) -> int:
    print(f"探测手柄: {js_path}")
    print("请推动摇杆、按按键，观察轴/按键编号。Ctrl+C 结束。\n")
    joy = Joystick(js_path)
    start = time.monotonic()
    last_axes: Dict[int, float] = {}
    last_buttons: Dict[int, bool] = {}

    try:
        while time.monotonic() - start < seconds:
            joy.poll()
            for number, value in joy.axes.items():
                if last_axes.get(number) != value:
                    print(f"axis {number}: {value:+.3f}")
                    last_axes[number] = value
            for number, pressed in joy.buttons.items():
                if last_buttons.get(number) != pressed:
                    print(f"button {number}: {'按下' if pressed else '松开'}")
                    last_buttons[number] = pressed
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        joy.close()

    print("\n本车默认遥控映射:")
    print("  右摇杆: axis 4=前进/后退, axis 3=左移/右移")
    print("  左摇杆: 自动扫描旋转轴(排除 2/3/4/5)")
    print("  退出: Back(button 6)")
    print("\n运行: python remote_tc377.py")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="手柄遥控 TC377 底盘")
    parser.add_argument("--port", default=DEFAULT_PORT, help="TC377 串口")
    parser.add_argument("--js", default=DEFAULT_JS, help="手柄设备路径")
    parser.add_argument("--max-linear", type=int, default=DEFAULT_MAX_LINEAR, help="前进/平移最大 ticks")
    parser.add_argument("--max-rotate", type=int, default=DEFAULT_MAX_ROTATE, help="旋转最大原始 w 值")
    parser.add_argument("--min-linear", type=int, default=DEFAULT_MIN_LINEAR, help="前进/平移最小 ticks，0 表示不限制")
    parser.add_argument("--min-rotate", type=int, default=DEFAULT_MIN_ROTATE, help="旋转最小原始 w 值，0 表示不限制")
    parser.add_argument("--deadzone", type=float, default=DEFAULT_DEADZONE, help="摇杆死区 0~1")
    parser.add_argument("--hz", type=float, default=DEFAULT_POLL_HZ, help="控制循环频率")
    parser.add_argument("--axis-forward", type=int, default=DEFAULT_AXIS_FORWARD, help="前进轴，默认右摇杆 axis 4")
    parser.add_argument("--axis-strafe", type=int, default=DEFAULT_AXIS_STRAFE, help="平移轴，默认右摇杆 axis 3")
    parser.add_argument(
        "--rotate-exclude",
        type=int,
        nargs="+",
        default=DEFAULT_ROTATE_EXCLUDE,
        help="旋转扫描时排除的轴，默认 2 3 4 5",
    )
    parser.add_argument(
        "--rotate-axes",
        type=int,
        nargs="+",
        default=None,
        help="手动指定旋转轴；默认自动扫描",
    )
    parser.add_argument("--sign-forward", type=float, default=DEFAULT_SIGN_FORWARD, help="前进轴符号")
    parser.add_argument("--sign-strafe", type=float, default=DEFAULT_SIGN_STRAFE, help="平移轴符号")
    parser.add_argument("--sign-rotate", type=float, default=DEFAULT_SIGN_ROTATE, help="旋转轴符号")
    parser.add_argument(
        "--exit-button",
        type=int,
        action="append",
        dest="exit_buttons",
        help="退出按钮，可多次指定；默认 Back=6",
    )
    parser.add_argument("--status-interval", type=float, default=DEFAULT_STATUS_INTERVAL, help="状态打印间隔（秒）")
    parser.add_argument("--debug-sticks", action="store_true", help="实时打印摇杆原始值")
    parser.add_argument("--probe", action="store_true", help="探测摇杆轴/按键编号后退出")
    parser.add_argument("--probe-seconds", type=float, default=10.0, help="探测模式持续时间")
    args = parser.parse_args()
    if not args.exit_buttons:
        args.exit_buttons = list(DEFAULT_EXIT_BUTTONS)
    return args


def print_help_banner(args: argparse.Namespace, js_path: str) -> None:
    print("=" * 50)
    print("TC377 手柄遥控")
    print(f"  手柄: {js_path}")
    print(f"  串口: {args.port}")
    print(f"  速度: linear 0~{args.max_linear}, rotate 0~{args.max_rotate}")
    print(f"  最小指令: linear={args.min_linear}, rotate={args.min_rotate}")
    print(f"  右摇杆: axis {args.axis_forward}=前进, axis {args.axis_strafe}=平移")
    if args.rotate_axes:
        print(f"  左摇杆: axis {args.rotate_axes}=旋转(手动)")
    else:
        print(f"  左摇杆: 自动扫描旋转(排除 axis {args.rotate_exclude})")
    print(f"  退出: Back(button {args.exit_buttons}) 或 Ctrl+C")
    print("=" * 50)
    print("请确认车轮悬空或周围无障碍物。\n")


def main() -> int:
    args = parse_args()

    all_js = sorted(glob.glob("/dev/input/js*"))
    js_path = find_js_device(args.js)
    if js_path is None:
        print("未找到手柄设备。", file=sys.stderr)
        print("请确认手柄已通过 USB 或蓝牙连接 Jetson。", file=sys.stderr)
        print("可检查: ls /dev/input/js*", file=sys.stderr)
        return 1
    if len(all_js) > 1:
        print(f"提示: 检测到多个手柄设备 {all_js}，当前使用 {js_path}")
        print("若左摇杆无反应，可尝试: python remote_tc377.py --js /dev/input/js1\n")

    if args.probe:
        return run_probe(js_path, args.probe_seconds)

    if not os.path.exists(args.port):
        print(f"未找到串口: {args.port}", file=sys.stderr)
        print("请确认 TC377 已上电并插入 USB 串口线。", file=sys.stderr)
        print("可检查: ls /dev/ttyUSB* /dev/ttyACM*", file=sys.stderr)
        return 1

    print_help_banner(args, js_path)
    joy = Joystick(js_path)

    try:
        with TC377Chassis(args.port) as car:
            print("已连接 TC377，开始读取手柄...\n")

            last_cmd = (0, 0, 0)
            interval = 1.0 / args.hz
            next_status = time.monotonic() + args.status_interval

            while True:
                joy.poll()

                if joy.any_button_pressed(args.exit_buttons):
                    car.stop()
                    print("\n检测到退出键，已停车。")
                    break

                cmd = sticks_to_xyw(joy, args)

                if args.debug_sticks:
                    print(f"[摇杆] {format_stick_debug(joy, args)} -> XYW {cmd}")

                if cmd != (0, 0, 0):
                    car.set_xyw_raw(*cmd)
                    if cmd != last_cmd and not args.debug_sticks:
                        print(f"XYW {cmd[0]} {cmd[1]} {cmd[2]}")
                elif last_cmd != (0, 0, 0):
                    car.stop()
                    if not args.debug_sticks:
                        print("VSTOP")

                last_cmd = cmd

                now = time.monotonic()
                if now >= next_status and not args.debug_sticks:
                    enc = car.get_encoders()
                    summary = "  ".join(
                        f"M{m} v={enc[m].velocity:4d}" for m in sorted(enc)
                    )
                    print(f"[状态] {summary}")
                    next_status = now + args.status_interval

                time.sleep(interval)

    except KeyboardInterrupt:
        print("\n退出中，已停车。")
        return 0
    except TC377Error as exc:
        print(f"通信失败: {exc}", file=sys.stderr)
        return 1
    finally:
        joy.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
