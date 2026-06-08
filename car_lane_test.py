#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
巡线场地测试 — 让小车沿车道线行驶指定距离。

在 Jetson 车上运行:
    python3 car_lane_test.py              # 默认速度 0.3 m/s，行驶 99 m
    python3 car_lane_test.py --dis 3      # 先短距离试跑（推荐第一次）
    python3 car_lane_test.py --speed 0.2  # 降速，巡线更稳

安全:
    运行中按车身【按键 3】紧急停车。
"""
import argparse
import os
import sys
import time

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from car_wrap_2026 import MyCar


def run_lane_test(speed: float, distance: float) -> None:
    car = None
    try:
        car = MyCar()
        car.STOP_PARAM = False
        car._stop_flag = False
        car.beep()
        time.sleep(0.5)
        car.arm.reset_position()
        car.reset_position()

        dis_start = car.get_distance()
        print(f"开始巡线: 速度={speed} m/s, 目标距离={distance} m")
        print(f"起点位姿: {car.get_odometry()}, 累计距离: {dis_start:.3f} m")
        print("按【按键 3】可随时停车")

        car.lane_dis_offset(speed=speed, dis_hold=distance)

        dis_end = car.get_distance()
        print(f"巡线结束位姿: {car.get_odometry()}")
        print(f"本次行驶: {dis_end - dis_start:.3f} m")
        if car._stop_flag:
            print("（已手动停车）")
    except KeyboardInterrupt:
        print("\n用户中断")
    finally:
        if car is not None:
            car.stop()
            car.close()
            print("车辆已停止，资源已释放")


def main():
    parser = argparse.ArgumentParser(description="巡线场地测试")
    parser.add_argument(
        "--speed",
        type=float,
        default=0.3,
        help="巡线前进速度 (m/s)，建议首次用 0.2",
    )
    parser.add_argument(
        "--dis",
        type=float,
        default=99.0,
        help="巡线距离 (m)，首次建议 3~5 米短跑",
    )
    args = parser.parse_args()
    run_lane_test(speed=args.speed, distance=args.dis)


if __name__ == "__main__":
    main()
