from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Measurement:
    """A single voltage/current/power snapshot from the load."""

    voltage_v: float
    current_a: float
    power_w: float

    def to_dict(self) -> dict[str, float]:
        return {
            "voltage_v": self.voltage_v,
            "current_a": self.current_a,
            "power_w": self.power_w,
        }


class InstrumentError(RuntimeError):
    """Raised when transport access or instrument communication fails."""

    pass
