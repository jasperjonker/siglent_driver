from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .core import InstrumentError, Measurement

try:
    import pyvisa  # type: ignore
except ImportError:  # pragma: no cover
    pyvisa = None


SiglentMode = Literal["current", "voltage", "power", "resistance", "led"]


def _siglent_mode_token(mode: SiglentMode) -> str:
    return {
        "current": "CURRent",
        "voltage": "VOLTage",
        "power": "POWer",
        "resistance": "RESistance",
        "led": "LED",
    }[mode]


@dataclass(slots=True)
class SiglentSDL1030:
    resource_name: str
    timeout_ms: int = 2000

    _rm: object | None = None
    _inst: object | None = None

    def open(self) -> None:
        if self._inst is not None:
            return
        if pyvisa is None:  # pragma: no cover
            raise InstrumentError("pyvisa is required for Siglent VISA support")
        self._rm = pyvisa.ResourceManager()
        self._inst = self._rm.open_resource(self.resource_name)
        self._inst.timeout = self.timeout_ms
        self._inst.read_termination = "\n"
        self._inst.write_termination = "\n"

    def close(self) -> None:
        if self._inst is not None:
            self._inst.close()
            self._inst = None
        if self._rm is not None:
            self._rm.close()
            self._rm = None

    def write(self, command: str) -> None:
        self._ensure_open()
        self._inst.write(command)

    def query(self, command: str) -> str:
        self._ensure_open()
        return self._inst.query(command).strip()

    def identify(self) -> str:
        return self.query("*IDN?")

    def set_input_enabled(self, enabled: bool) -> None:
        self.write(f":SOUR:INP:STAT {'ON' if enabled else 'OFF'}")

    def is_input_enabled(self) -> bool:
        return self.query(":SOUR:INP:STAT?") == "1"

    def set_mode(self, mode: SiglentMode) -> None:
        self.write(f":SOUR:FUNC {_siglent_mode_token(mode)}")

    def get_mode(self) -> str:
        return self.query(":SOUR:FUNC?")

    def set_current(self, amps: float) -> None:
        self.write(f":SOUR:CURR:LEV:IMM {amps}")

    def set_voltage(self, volts: float) -> None:
        self.write(f":SOUR:VOLT:LEV:IMM {volts}")

    def set_power(self, watts: float) -> None:
        self.write(f":SOUR:POW:LEV:IMM {watts}")

    def set_resistance(self, ohms: float) -> None:
        self.write(f":SOUR:RES:LEV:IMM {ohms}")

    def measure_voltage(self) -> float:
        return float(self.query("MEAS:VOLT:DC?"))

    def measure_current(self) -> float:
        return float(self.query("MEAS:CURR:DC?"))

    def measure_power(self) -> float:
        return float(self.query("MEAS:POW:DC?"))

    def measure_resistance(self) -> float:
        return float(self.query("MEAS:RES:DC?"))

    def measure_all(self) -> Measurement:
        return Measurement(
            voltage_v=self.measure_voltage(),
            current_a=self.measure_current(),
            power_w=self.measure_power(),
        )

    def configure_list_mode(
        self,
        *,
        mode: Literal["current", "voltage", "power", "resistance"],
        levels: list[float],
        widths_s: list[float],
        count: int = 1,
    ) -> None:
        if len(levels) != len(widths_s):
            raise ValueError("levels and widths_s must have the same length")
        if not levels:
            raise ValueError("At least one list step is required")
        self.write(f":SOUR:LIST:MODE {_siglent_mode_token(mode)}")
        self.write(f":SOUR:LIST:COUN {count}")
        self.write(f":SOUR:LIST:STEP {len(levels)}")
        for idx, (level, width) in enumerate(zip(levels, widths_s, strict=True), start=1):
            self.write(f":SOUR:LIST:LEV {idx},{level}")
            self.write(f":SOUR:LIST:WID {idx},{width}")

    def enter_list_mode(self) -> None:
        self.write(":SOUR:LIST:STAT:ON")

    def set_trigger_source(self, source: Literal["manual", "external", "bus"]) -> None:
        token = {"manual": "MANUal", "external": "EXTernal", "bus": "BUS"}[source]
        self.write(f"TRIG:SOUR {token}")

    def trigger(self) -> None:
        self.write("*TRG")

    def _ensure_open(self) -> None:
        if self._inst is None:
            raise InstrumentError("Siglent VISA resource is not open")
