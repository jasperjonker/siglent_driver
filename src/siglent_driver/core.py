from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Measurement:
    voltage_v: float
    current_a: float
    power_w: float


class InstrumentError(RuntimeError):
    pass
