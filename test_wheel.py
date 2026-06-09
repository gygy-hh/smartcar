#!/usr/bin/env python3
"""TC377 单轮测试脚本。

依次测试 M1~M4，检查每个电机是否能正常旋转。

用法：
  python test_wheel.py
  python test_wheel.py --speed 80 --duration 1.0
  python test_wheel.py --motor 3
"""

from __future__ import annotations

import argparse
import time

from jetson_tc377 import TC377Chassis, TC377Error

DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_SPEED = 80
DEFAULT_DURATION = 0.5
DEFAULT_PAUSE = 0.5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TC377 单轮测试")
    parser.add_argument("--port", default=DEFAULT_PORT, help="串口路径")
    parser.add_argument("--speed", type=int, default=DEFAULT_SPEED, help="单轮速度 ticks/50ms")
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION, help="每个轮子运行时间（秒）")
    parser.add_argument("--pause", type=float, default=DEFAULT_PAUSE, help="每个轮子之间的间隔（秒）")
    parser.add_argument("--motor", type=int, choices=[1, 2, 3, 4], help="只测试指定电机")
    parser.add_argument("--no-countdown", action="store_true", help="跳过 3 秒倒计时")
    return parser.parse_args()


def countdown(seconds: int = 3) -> None:
    for i in range(seconds, 0, -1):
        print(f"  {i}...")
        time.sleep(1.0)


def test_motor(car: TC377Chassis, motor: int, speed: int, duration: float) -> int:
    before = car.get_encoder(motor).position
    print(f"\n>>> M{motor} 速度 {speed}，持续 {duration}s")
    car.set_wheel_speed(motor, speed)
    time.sleep(duration)
    car.stop()
    time.sleep(0.2)

    after = car.get_encoder(motor)
    delta = after.position - before
    print(f"  pos={after.position}  vel={after.velocity}  delta={delta:+d}")
    return delta


def main() -> int:
    args = parse_args()
    motors = [args.motor] if args.motor else [1, 2, 3, 4]

    print("=" * 50)
    print("TC377 单轮测试")
    print("请确认：TC377 已上电，车轮已悬空")
    print(f"测试参数: 速度={args.speed}, 持续={args.duration}s")
    print("=" * 50)

    if not args.no_countdown:
        print("\n即将开始，按 Ctrl+C 可取消")
        try:
            countdown(3)
        except KeyboardInterrupt:
            print("\n已取消")
            return 0

    try:
        with TC377Chassis(args.port) as car:
            print(f"\n已连接串口: {args.port}")

            deltas = []
            for motor in motors:
                delta = test_motor(car, motor, args.speed, args.duration)
                deltas.append((motor, delta))
                time.sleep(args.pause)

            if len(deltas) > 1:
                values = [d for _, d in deltas]
                avg = sum(values) / len(values)
                print("\n=== 幅度一致性 ===")
                print(f"  平均增量: {avg:.1f}")
                for motor, delta in deltas:
                    diff_pct = abs(delta - avg) / max(abs(avg), 1) * 100
                    flag = "OK" if diff_pct < 20 else "偏差大"
                    print(f"  M{motor}: delta={delta:+d}  与均值差 {diff_pct:.1f}%  [{flag}]")

            print("\n测试完成，底盘已停车。")

    except TC377Error as exc:
        print(f"\n测试失败: {exc}")
        return 1
    except KeyboardInterrupt:
        print("\n用户中断")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
