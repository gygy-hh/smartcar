#!/usr/bin/env python3
"""测试前进时四轮编码器增量是否一致。"""

from __future__ import annotations

import argparse
import time

from jetson_tc377 import TC377Chassis, TC377Error

DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_SPEED = 80
DEFAULT_DURATION = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="前进幅度一致性测试")
    parser.add_argument("--port", default=DEFAULT_PORT, help="串口路径")
    parser.add_argument("--speed", type=int, default=DEFAULT_SPEED, help="XYW 前进 ticks/50ms")
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION, help="持续时间（秒）")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("请确认：TC377 已上电，车轮已悬空")
    print(f"测试参数: XYW {args.speed} 0 0, 持续 {args.duration}s\n")

    try:
        with TC377Chassis(args.port) as car:
            before = car.get_encoders()
            print("=== 前进前 ===")
            for motor in sorted(before):
                print(f"  M{motor}: pos={before[motor].position}")

            print(f"\n>>> 前进 XYW {args.speed} 0 0，持续 {args.duration}s")
            car.set_xyw_raw(args.speed, 0, 0)
            time.sleep(args.duration)
            car.stop()
            time.sleep(0.2)

            after = car.get_encoders()
            print("\n=== 前进后 ===")
            deltas = []
            for motor in sorted(after):
                delta = after[motor].position - before[motor].position
                deltas.append(delta)
                print(f"  M{motor}: pos={after[motor].position}  delta={delta:+d}")

            avg = sum(deltas) / len(deltas)
            print("\n=== 幅度一致性 ===")
            print(f"  平均增量: {avg:.1f}")
            for motor, delta in enumerate(deltas, 1):
                diff_pct = abs(delta - avg) / max(abs(avg), 1) * 100
                flag = "OK" if diff_pct < 20 else "偏差大"
                print(f"  M{motor}: delta={delta:+d}  与均值差 {diff_pct:.1f}%  [{flag}]")

    except TC377Error as exc:
        print(f"测试失败: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
