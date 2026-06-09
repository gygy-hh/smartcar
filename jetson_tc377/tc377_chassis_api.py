#!/usr/bin/env python3
"""Jetson-side serial API for the TC377 chassis controller.

The firmware command layer uses ASCII commands over the debug UART.  This
module wraps the chassis-related commands so upper-level Jetson code can call a
small Python API similar to ``docs/api.md``.

Coordinate convention for ``set_velocity(x, y, z)`` follows ``docs/api.md``:

- ``x``: forward m/s is positive
- ``y``: left strafe m/s is positive
- ``z``: counter-clockwise rad/s is positive

The TC377 firmware command ``XYW`` uses ``y`` right-positive and ``w``
clockwise-positive, so this wrapper flips those two signs automatically.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

try:
    import serial
except ImportError:  # pragma: no cover - dependency message path
    serial = None


ENCODER_RE = re.compile(r"ENC M(?P<motor>[1-4]) pos=(?P<pos>-?\d+) vel=(?P<vel>-?\d+)")


class TC377Error(RuntimeError):
    """Base exception for TC377 serial API errors."""


class TC377CommandError(TC377Error):
    """Raised when firmware returns ``ERR ...`` for a command."""


class TC377TimeoutError(TC377Error):
    """Raised when firmware does not return an expected response in time."""


@dataclass(frozen=True)
class EncoderSample:
    motor: int
    position: int
    velocity: int


class TC377Chassis:
    """Serial wrapper for the TC377 lower-controller chassis commands."""

    STOP_PARAM = True

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 0.05,
        command_timeout: float = 0.50,
        ticks_per_meter: float = 7800.0,
        control_period_s: float = 0.05,
        max_target: int = 1000,
        max_omega_raw: int = 9000,
    ) -> None:
        if serial is None:
            raise TC377Error("pyserial is required: python -m pip install pyserial")

        self.port_name = port
        self.baudrate = baudrate
        self.command_timeout = command_timeout
        self.ticks_per_meter = ticks_per_meter
        self.control_period_s = control_period_s
        self.max_target = max_target
        self.max_omega_raw = max_omega_raw
        self._serial: Any = serial.Serial(port, baudrate, timeout=timeout)
        time.sleep(0.2)
        self.flush_input()

    def __enter__(self) -> "TC377Chassis":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def close(self) -> None:
        if getattr(self, "_serial", None) is not None and self._serial.is_open:
            try:
                self.stop()
            except TC377Error:
                pass
            self._serial.close()

    def flush_input(self) -> None:
        if hasattr(self._serial, "reset_input_buffer"):
            self._serial.reset_input_buffer()
            return
        while self._serial.readline():
            pass

    def send_line(self, command: str) -> None:
        self._serial.write((command.strip() + "\r\n").encode("ascii"))
        self._serial.flush()

    def read_available_lines(self, seconds: float) -> List[str]:
        deadline = time.monotonic() + seconds
        lines: List[str] = []
        while time.monotonic() < deadline:
            raw = self._serial.readline()
            if not raw:
                continue
            line = raw.decode("ascii", errors="ignore").strip()
            if line:
                lines.append(line)
        return lines

    def command(self, command: str, ok_prefixes: Iterable[str], timeout: Optional[float] = None) -> str:
        deadline = time.monotonic() + (self.command_timeout if timeout is None else timeout)
        prefixes = tuple(ok_prefixes)
        seen: List[str] = []

        self.send_line(command)
        while time.monotonic() < deadline:
            raw = self._serial.readline()
            if not raw:
                continue
            line = raw.decode("ascii", errors="ignore").strip()
            if not line:
                continue
            seen.append(line)
            if line.startswith("ERR"):
                raise TC377CommandError("{0}: {1}".format(command, line))
            if any(line.startswith(prefix) for prefix in prefixes):
                return line

        raise TC377TimeoutError(
            "timeout waiting for {0!r}; expected {1}, seen {2}".format(command, prefixes, seen)
        )

    def _linear_to_ticks(self, meters_per_second: float) -> int:
        return int(round(meters_per_second * self.ticks_per_meter * self.control_period_s))

    def _angular_to_firmware_w(self, radians_per_second: float) -> int:
        return int(round(radians_per_second * self.ticks_per_meter * self.control_period_s))

    def _check_target(self, value: int, name: str) -> None:
        if value < -self.max_target or value > self.max_target:
            raise ValueError("{0} out of range: {1}, expected +/-{2}".format(name, value, self.max_target))

    def _check_omega(self, value: int) -> None:
        if value < -self.max_omega_raw or value > self.max_omega_raw:
            raise ValueError("w out of range: {0}, expected +/-{1}".format(value, self.max_omega_raw))

    def set_velocity(self, x: float, y: float, z: float) -> str:
        """Set chassis velocity using ``docs/api.md`` convention.

        ``x`` and ``y`` are m/s. ``z`` is rad/s, counter-clockwise positive.
        The conversion to firmware target units uses ``ticks_per_meter``.
        Calibrate ``ticks_per_meter`` for the actual wheel and encoder setup.
        """

        x_ticks = self._linear_to_ticks(x)
        y_right_ticks = -self._linear_to_ticks(y)
        w_clockwise_raw = -self._angular_to_firmware_w(z)
        return self.set_xyw_raw(x_ticks, y_right_ticks, w_clockwise_raw)

    def set_xyw_raw(self, x_ticks: int, y_right_ticks: int, w_clockwise_raw: int) -> str:
        """Send raw firmware ``XYW`` target units.

        ``x_ticks`` and ``y_right_ticks`` are wheel target units in ticks/50ms.
        ``w_clockwise_raw`` is the firmware rotation input before TC377 applies
        the ``(L + W)`` mecanum rotation coefficient.
        """

        self._check_target(x_ticks, "x")
        self._check_target(y_right_ticks, "y")
        self._check_omega(w_clockwise_raw)
        return self.command(
            "XYW {0} {1} {2}".format(x_ticks, y_right_ticks, w_clockwise_raw),
            ("OK XYW",),
        )

    def stop(self) -> str:
        return self.command("VSTOP", ("OK VSTOP",))

    def brake(self) -> str:
        return self.command("BRAKE", ("OK BRAKE",))

    def set_velocity_for_duration(self, x: float, y: float, z: float, duration: float = 1.0) -> None:
        self.set_velocity(x, y, z)
        time.sleep(duration)
        self.stop()

    def move_time(self, sp: Iterable[float], dur_time: float = 1.0, stop: Optional[bool] = None) -> None:
        x, y, z = self._unpack_speed(sp)
        self.set_velocity(x, y, z)
        time.sleep(dur_time)
        if self._should_stop(stop):
            self.stop()

    def move_base(
        self,
        sp: Iterable[float],
        end_function: Callable[[], bool],
        stop: Optional[bool] = None,
        poll_interval: float = 0.02,
    ) -> None:
        x, y, z = self._unpack_speed(sp)
        self.set_velocity(x, y, z)
        try:
            while not end_function():
                time.sleep(poll_interval)
        finally:
            if self._should_stop(stop):
                self.stop()

    def move_distance(self, sp: Iterable[float], dis: float = 0.1, stop: Optional[bool] = None) -> None:
        x, y, z = self._unpack_speed(sp)
        linear_speed = (x * x + y * y) ** 0.5
        if linear_speed <= 0.0:
            raise ValueError("move_distance requires non-zero x/y speed")
        self.move_time((x, y, z), dis / linear_speed, stop=stop)

    def delay(self, time_hold: float) -> None:
        time.sleep(time_hold)

    def set_wheel_speed(self, motor: int, ticks_per_period: int) -> str:
        if motor < 1 or motor > 4:
            raise ValueError("motor must be 1..4")
        self._check_target(ticks_per_period, "ticks_per_period")
        return self.command("V{0} {1}".format(motor, ticks_per_period), ("OK V{0}".format(motor),))

    def set_all_wheel_speed(self, ticks_per_period: int) -> str:
        self._check_target(ticks_per_period, "ticks_per_period")
        return self.command("VALL {0}".format(ticks_per_period), ("OK VALL",))

    def get_encoders(self, timeout: Optional[float] = None) -> Dict[int, EncoderSample]:
        deadline = time.monotonic() + (self.command_timeout if timeout is None else timeout)
        samples: Dict[int, EncoderSample] = {}
        self.send_line("ENC?")
        while time.monotonic() < deadline and len(samples) < 4:
            raw = self._serial.readline()
            if not raw:
                continue
            line = raw.decode("ascii", errors="ignore").strip()
            match = ENCODER_RE.search(line)
            if not match:
                continue
            motor = int(match.group("motor"))
            samples[motor] = EncoderSample(
                motor=motor,
                position=int(match.group("pos")),
                velocity=int(match.group("vel")),
            )
        if len(samples) < 4:
            raise TC377TimeoutError("timeout waiting for ENC? response, got {0} motors".format(len(samples)))
        return samples

    def get_encoder(self, motor: int, timeout: Optional[float] = None) -> EncoderSample:
        if motor < 1 or motor > 4:
            raise ValueError("motor must be 1..4")
        return self.get_encoders(timeout=timeout)[motor]

    def reset_pid(self) -> str:
        return self.command("PIDRST", ("OK PIDRST",))

    def set_pid(self, motor: int, kp: int, ki: int) -> str:
        if motor < 1 or motor > 4:
            raise ValueError("motor must be 1..4")
        return self.command("PID {0} {1} {2}".format(motor, kp, ki), ("OK PID M{0}".format(motor),))

    def set_feedforward(self, motor: int, dead: int, gain: int) -> str:
        """Set feedforward gain.

        ``dead`` is kept for firmware command compatibility and is ignored by
        current firmware; use ``0`` when calling this API.
        """

        if motor < 1 or motor > 4:
            raise ValueError("motor must be 1..4")
        return self.command("FF {0} {1} {2}".format(motor, dead, gain), ("OK FF M{0}".format(motor),))

    @staticmethod
    def _unpack_speed(sp: Iterable[float]) -> Tuple[float, float, float]:
        values = list(sp)
        if len(values) != 3:
            raise ValueError("speed vector must contain [x, y, z]")
        return float(values[0]), float(values[1]), float(values[2])

    def _should_stop(self, stop: Optional[bool]) -> bool:
        return self.STOP_PARAM if stop is None else stop


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Small TC377 chassis serial smoke test.")
    parser.add_argument("--port", required=True, help="Serial port, for example /dev/ttyUSB0 or COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--ticks-per-meter", type=float, default=7800.0)
    parser.add_argument("--x", type=float, default=0.0)
    parser.add_argument("--y", type=float, default=0.0)
    parser.add_argument("--z", type=float, default=0.0)
    parser.add_argument("--duration", type=float, default=0.5)
    args = parser.parse_args()

    with TC377Chassis(args.port, args.baud, ticks_per_meter=args.ticks_per_meter) as car:
        car.set_velocity_for_duration(args.x, args.y, args.z, args.duration)
        print(car.get_encoders())
