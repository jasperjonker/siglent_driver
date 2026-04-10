from __future__ import annotations

from dataclasses import dataclass
import errno
from enum import Enum, StrEnum
import logging
import os
import time
from typing import Literal, Protocol, TypeAlias

from .core import InstrumentError, Measurement

try:
    import pyvisa  # type: ignore
except ImportError:  # pragma: no cover
    pyvisa = None


logger = logging.getLogger(__name__)


class LoadMode(StrEnum):
    CC = "current"
    CV = "voltage"
    CP = "power"
    CR = "resistance"
    LED = "led"


class TransientMode(StrEnum):
    CC = "current"
    CV = "voltage"
    CP = "power"
    CR = "resistance"


class TransientWaveform(StrEnum):
    CONTINUOUS = "continuous"
    PULSE = "pulse"
    TOGGLE = "toggle"


class BatteryMode(StrEnum):
    CC = "current"
    CP = "power"
    CR = "resistance"
    DCR = "dcr"


class TriggerSource(StrEnum):
    MANUAL = "manual"
    EXTERNAL = "external"
    BUS = "bus"


class ProtectionType(StrEnum):
    CURRENT = "current"
    POWER = "power"


CurrentRangeTarget = Literal[
    "current",
    "voltage",
    "power",
    "resistance",
    "current_transient",
    "voltage_transient",
    "power_transient",
    "resistance_transient",
    "battery",
    "list",
    "ocp",
    "opp",
    "external",
]
VoltageRangeTarget = CurrentRangeTarget
ResistanceRangeTarget = Literal["resistance", "resistance_transient", "battery", "list"]


class ResistanceRange(StrEnum):
    LOW = "low"
    MIDDLE = "middle"
    HIGH = "high"
    UPPER = "upper"


class WaveformMetric(StrEnum):
    CURRENT = "current"
    VOLTAGE = "voltage"
    POWER = "power"
    RESISTANCE = "resistance"


class CurrentRange(float, Enum):
    A5 = 5.0
    A30 = 30.0


class VoltageRange(float, Enum):
    V36 = 36.0
    V150 = 150.0


LoadModeLike: TypeAlias = LoadMode | Literal["current", "voltage", "power", "resistance", "led"]
TransientModeLike: TypeAlias = TransientMode | Literal["current", "voltage", "power", "resistance"]
TransientWaveformLike: TypeAlias = TransientWaveform | Literal["continuous", "pulse", "toggle"]
BatteryModeLike: TypeAlias = BatteryMode | Literal["current", "power", "resistance", "dcr"]
TriggerSourceLike: TypeAlias = TriggerSource | Literal["manual", "external", "bus"]
ProtectionTypeLike: TypeAlias = ProtectionType | Literal["current", "power"]
ResistanceRangeLike: TypeAlias = ResistanceRange | Literal["low", "middle", "high", "upper"]
WaveformMetricLike: TypeAlias = WaveformMetric | Literal["current", "voltage", "power", "resistance"]
CurrentRangeLike: TypeAlias = CurrentRange | float
VoltageRangeLike: TypeAlias = VoltageRange | float


CURRENT_RANGE_VALUES = tuple(float(value) for value in CurrentRange)
VOLTAGE_RANGE_VALUES = tuple(float(value) for value in VoltageRange)


def _siglent_mode_token(mode: LoadModeLike | TransientModeLike | WaveformMetricLike) -> str:
    return {
        "current": "CURRent",
        "voltage": "VOLTage",
        "power": "POWer",
        "resistance": "RESistance",
        "led": "LED",
    }[str(mode)]


def _battery_mode_token(mode: BatteryModeLike) -> str:
    return {
        "current": "CURRent",
        "power": "POWer",
        "resistance": "RESistance",
        "dcr": "DCR",
    }[str(mode)]


def _transient_waveform_token(mode: TransientWaveformLike) -> str:
    return {
        "continuous": "CONTinuous",
        "pulse": "PULSe",
        "toggle": "TOGGle",
    }[str(mode)]


def _trigger_source_token(source: TriggerSourceLike) -> str:
    return {
        "manual": "MANUal",
        "external": "EXTernal",
        "bus": "BUS",
    }[str(source)]


def _resistance_range_token(value: ResistanceRangeLike) -> str:
    return str(value).upper()


def _boolean_token(value: bool) -> str:
    return "ON" if value else "OFF"


def _canonical_current_range(value: CurrentRangeLike) -> CurrentRange:
    return CurrentRange.A5 if float(value) <= float(CurrentRange.A5) else CurrentRange.A30


def _canonical_voltage_range(value: VoltageRangeLike) -> VoltageRange:
    return VoltageRange.V36 if float(value) <= float(VoltageRange.V36) else VoltageRange.V150


def _current_range_root(target: CurrentRangeTarget) -> str:
    return {
        "current": "CURRent",
        "voltage": "VOLTage",
        "power": "POWer",
        "resistance": "RESistance",
        "current_transient": "CURRent:TRANsient",
        "voltage_transient": "VOLTage:TRANsient",
        "power_transient": "POWer:TRANsient",
        "resistance_transient": "RESistance:TRANsient",
        "battery": "BATTery",
        "list": "LIST",
        "ocp": "OCP",
        "opp": "OPP",
        "external": "EXT",
    }[target]


def _voltage_range_root(target: VoltageRangeTarget) -> str:
    return _current_range_root(target)


def _resistance_range_root(target: ResistanceRangeTarget) -> str:
    return {
        "resistance": "RESistance",
        "resistance_transient": "RESistance:TRANsient",
        "battery": "BATTery",
        "list": "LIST",
    }[target]


def _transient_root(mode: TransientModeLike) -> str:
    return f"{_siglent_mode_token(mode)}:TRANsient"


def _protection_root(kind: ProtectionTypeLike) -> str:
    return f"{_siglent_mode_token(kind)}:PROTection"


class _InstrumentTransport(Protocol):
    def write(self, command: str) -> None: ...

    def query(self, command: str) -> str: ...

    def close(self) -> None: ...


@dataclass(slots=True)
class _VisaTransport:
    resource_name: str
    timeout_ms: int
    backend: str | None = None

    _rm: object | None = None
    _inst: object | None = None

    def __post_init__(self) -> None:
        if pyvisa is None:  # pragma: no cover
            raise InstrumentError("pyvisa is required for Siglent VISA support")
        try:
            self._rm = pyvisa.ResourceManager(self.backend) if self.backend else pyvisa.ResourceManager()
        except ValueError as exc:  # pragma: no cover
            raise InstrumentError(
                "No VISA backend is available. Ensure `pyvisa-py` or a compatible vendor VISA "
                "implementation is installed, or use a Linux USBTMC device path like `/dev/usbtmc0`."
            ) from exc

        try:
            self._inst = self._rm.open_resource(self.resource_name)
        except Exception as exc:
            if self._rm is not None:
                self._rm.close()
                self._rm = None
            raise InstrumentError(
                f"Failed to open VISA resource `{self.resource_name}`"
                f" using backend `{self.backend or 'default'}`: {exc}"
            ) from exc

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
        if self._inst is None:
            raise InstrumentError("Siglent VISA resource is not open")
        self._inst.write(command)

    def query(self, command: str) -> str:
        if self._inst is None:
            raise InstrumentError("Siglent VISA resource is not open")
        return self._inst.query(command).strip()


@dataclass(slots=True)
class _UsbTmcTransport:
    device_path: str
    timeout_ms: int

    _fd: int | None = None

    def __post_init__(self) -> None:
        self._fd = os.open(self.device_path, os.O_RDWR | os.O_NONBLOCK)

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def write(self, command: str) -> None:
        if self._fd is None:
            raise InstrumentError("Siglent USBTMC device is not open")
        os.write(self._fd, f"{command}\n".encode())

    def query(self, command: str) -> str:
        if self._fd is None:
            raise InstrumentError("Siglent USBTMC device is not open")
        self.write(command)
        deadline = time.monotonic() + (self.timeout_ms / 1000)
        while time.monotonic() < deadline:
            try:
                data = os.read(self._fd, 65536)
            except OSError as exc:
                if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK, errno.ETIMEDOUT):
                    raise InstrumentError(f"Failed while reading response from {self.device_path}") from exc
                data = b""
            if data:
                return data.decode(errors="replace").strip()
            time.sleep(0.01)
        raise InstrumentError(f"Timed out waiting for response from {self.device_path}")


@dataclass(slots=True)
class SiglentSDL1030:
    """SCPI driver for the Siglent SDL1030X electronic load."""

    resource_name: str
    timeout_ms: int = 2000
    visa_backend: str | None = None

    _transport: _InstrumentTransport | None = None

    def __enter__(self) -> SiglentSDL1030:
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def open(self) -> None:
        if self._transport is not None:
            logger.debug("Instrument already open: %s", self.resource_name)
            return
        try:
            if self.resource_name.startswith("/dev/usbtmc"):
                self._transport = _UsbTmcTransport(self.resource_name, self.timeout_ms)
                logger.info("Opened SDL1030 transport via USBTMC: %s", self.resource_name)
                return
            self._transport = _VisaTransport(
                self.resource_name,
                self.timeout_ms,
                backend=self.visa_backend,
            )
            logger.info(
                "Opened SDL1030 transport via VISA: resource=%s backend=%s",
                self.resource_name,
                self.visa_backend or "default",
            )
        except OSError as exc:
            raise InstrumentError(f"Failed to open instrument transport `{self.resource_name}`") from exc

    def close(self) -> None:
        if self._transport is not None:
            logger.info("Closing SDL1030 transport: %s", self.resource_name)
            self._transport.close()
            self._transport = None

    def write(self, command: str) -> None:
        self._ensure_open()
        logger.debug("SCPI write: %s", command)
        self._transport.write(command)

    def query(self, command: str) -> str:
        self._ensure_open()
        logger.debug("SCPI query: %s", command)
        response = self._transport.query(command)
        logger.debug("SCPI response: %s -> %s", command, response)
        return response

    def identify(self) -> str:
        return self.query("*IDN?")

    def reset(self) -> None:
        self.write("*RST")

    def clear_status(self) -> None:
        self.write("*CLS")

    def wait_until_complete(self) -> bool:
        return self.query("*OPC?") == "1"

    def set_input_enabled(self, enabled: bool) -> None:
        self.write(f":SOUR:INP:STAT {_boolean_token(enabled)}")

    def is_input_enabled(self) -> bool:
        return self.query(":SOUR:INP:STAT?") == "1"

    def set_short_enabled(self, enabled: bool) -> None:
        self.write(f":SOUR:SHOR:STAT {_boolean_token(enabled)}")

    def is_short_enabled(self) -> bool:
        return self.query(":SOUR:SHOR:STAT?") == "1"

    def set_mode(self, mode: LoadModeLike) -> None:
        self.write(f":SOUR:FUNC {_siglent_mode_token(mode)}")

    def get_mode(self) -> str:
        return self.query(":SOUR:FUNC?")

    def set_transient_function(self, mode: TransientModeLike) -> None:
        self.write(f":SOUR:FUNC:TRAN {_siglent_mode_token(mode)}")

    def get_transient_function(self) -> str:
        return self.query(":SOUR:FUNC:TRAN?")

    def set_current(self, amps: float) -> None:
        self.write(f":SOUR:CURR:LEV:IMM {amps}")

    def get_current(self) -> float:
        return float(self.query(":SOUR:CURR:LEV:IMM?"))

    def set_voltage(self, volts: float) -> None:
        self.write(f":SOUR:VOLT:LEV:IMM {volts}")

    def get_voltage(self) -> float:
        return float(self.query(":SOUR:VOLT:LEV:IMM?"))

    def set_power(self, watts: float) -> None:
        self.write(f":SOUR:POW:LEV:IMM {watts}")

    def get_power(self) -> float:
        return float(self.query(":SOUR:POW:LEV:IMM?"))

    def set_resistance(self, ohms: float) -> None:
        self.write(f":SOUR:RES:LEV:IMM {ohms}")

    def get_resistance(self) -> float:
        return float(self.query(":SOUR:RES:LEV:IMM?"))

    def set_current_range(self, target: CurrentRangeTarget, amps: CurrentRangeLike) -> None:
        root = _current_range_root(target)
        self.write(f":SOUR:{root}:IRANG {float(_canonical_current_range(amps))}")

    def get_current_range(self, target: CurrentRangeTarget) -> float:
        return float(self.query(f":SOUR:{_current_range_root(target)}:IRANG?"))

    def set_voltage_range(self, target: VoltageRangeTarget, volts: VoltageRangeLike) -> None:
        root = _voltage_range_root(target)
        self.write(f":SOUR:{root}:VRANG {float(_canonical_voltage_range(volts))}")

    def get_voltage_range(self, target: VoltageRangeTarget) -> float:
        return float(self.query(f":SOUR:{_voltage_range_root(target)}:VRANG?"))

    def set_resistance_range(self, target: ResistanceRangeTarget, value: ResistanceRangeLike) -> None:
        root = _resistance_range_root(target)
        self.write(f":SOUR:{root}:RRANG {_resistance_range_token(value)}")

    def get_resistance_range(self, target: ResistanceRangeTarget) -> str:
        return self.query(f":SOUR:{_resistance_range_root(target)}:RRANG?")

    def set_current_slew(self, amps_per_us: float) -> None:
        self.write(f":SOUR:CURR:SLEW:BOTH {amps_per_us}")

    def set_current_slew_positive(self, amps_per_us: float) -> None:
        self.write(f":SOUR:CURR:SLEW:POS {amps_per_us}")

    def get_current_slew_positive(self) -> float:
        return float(self.query(":SOUR:CURR:SLEW:POS?"))

    def set_current_slew_negative(self, amps_per_us: float) -> None:
        self.write(f":SOUR:CURR:SLEW:NEG {amps_per_us}")

    def get_current_slew_negative(self) -> float:
        return float(self.query(":SOUR:CURR:SLEW:NEG?"))

    def set_transient_waveform_mode(self, mode: TransientModeLike, waveform: TransientWaveformLike) -> None:
        self.write(f":SOUR:{_transient_root(mode)}:MODE {_transient_waveform_token(waveform)}")

    def get_transient_waveform_mode(self, mode: TransientModeLike) -> str:
        return self.query(f":SOUR:{_transient_root(mode)}:MODE?")

    def set_transient_a_level(self, mode: TransientModeLike, value: float) -> None:
        self.write(f":SOUR:{_transient_root(mode)}:ALEV {value}")

    def get_transient_a_level(self, mode: TransientModeLike) -> float:
        return float(self.query(f":SOUR:{_transient_root(mode)}:ALEV?"))

    def set_transient_b_level(self, mode: TransientModeLike, value: float) -> None:
        self.write(f":SOUR:{_transient_root(mode)}:BLEV {value}")

    def get_transient_b_level(self, mode: TransientModeLike) -> float:
        return float(self.query(f":SOUR:{_transient_root(mode)}:BLEV?"))

    def set_transient_a_width(self, mode: TransientModeLike, seconds: float) -> None:
        self.write(f":SOUR:{_transient_root(mode)}:AWID {seconds}")

    def get_transient_a_width(self, mode: TransientModeLike) -> float:
        return float(self.query(f":SOUR:{_transient_root(mode)}:AWID?"))

    def set_transient_b_width(self, mode: TransientModeLike, seconds: float) -> None:
        self.write(f":SOUR:{_transient_root(mode)}:BWID {seconds}")

    def get_transient_b_width(self, mode: TransientModeLike) -> float:
        return float(self.query(f":SOUR:{_transient_root(mode)}:BWID?"))

    def configure_transient(
        self,
        mode: TransientModeLike,
        waveform: TransientWaveformLike,
        a_level: float,
        b_level: float,
        a_width_s: float,
        b_width_s: float,
    ) -> None:
        self.set_transient_function(mode)
        self.set_transient_waveform_mode(mode, waveform)
        self.set_transient_a_level(mode, a_level)
        self.set_transient_b_level(mode, b_level)
        self.set_transient_a_width(mode, a_width_s)
        self.set_transient_b_width(mode, b_width_s)

    def set_current_transient_slew_positive(self, amps_per_us: float) -> None:
        self.write(f":SOUR:{_transient_root('current')}:SLEW:POS {amps_per_us}")

    def get_current_transient_slew_positive(self) -> float:
        return float(self.query(f":SOUR:{_transient_root('current')}:SLEW:POS?"))

    def set_current_transient_slew_negative(self, amps_per_us: float) -> None:
        self.write(f":SOUR:{_transient_root('current')}:SLEW:NEG {amps_per_us}")

    def get_current_transient_slew_negative(self) -> float:
        return float(self.query(f":SOUR:{_transient_root('current')}:SLEW:NEG?"))

    def set_protection_enabled(self, kind: ProtectionTypeLike, enabled: bool) -> None:
        self.write(f":SOUR:{_protection_root(kind)}:STAT {_boolean_token(enabled)}")

    def is_protection_enabled(self, kind: ProtectionTypeLike) -> bool:
        return self.query(f":SOUR:{_protection_root(kind)}:STAT?") == "1"

    def set_protection_level(self, kind: ProtectionTypeLike, value: float) -> None:
        self.write(f":SOUR:{_protection_root(kind)}:LEV {value}")

    def get_protection_level(self, kind: ProtectionTypeLike) -> float:
        return float(self.query(f":SOUR:{_protection_root(kind)}:LEV?"))

    def set_protection_delay(self, kind: ProtectionTypeLike, seconds: float) -> None:
        self.write(f":SOUR:{_protection_root(kind)}:DEL {seconds}")

    def get_protection_delay(self, kind: ProtectionTypeLike) -> float:
        return float(self.query(f":SOUR:{_protection_root(kind)}:DEL?"))

    def set_current_protection_enabled(self, enabled: bool) -> None:
        self.set_protection_enabled("current", enabled)

    def is_current_protection_enabled(self) -> bool:
        return self.is_protection_enabled("current")

    def set_current_protection_level(self, amps: float) -> None:
        self.set_protection_level("current", amps)

    def get_current_protection_level(self) -> float:
        return self.get_protection_level("current")

    def set_current_protection_delay(self, seconds: float) -> None:
        self.set_protection_delay("current", seconds)

    def get_current_protection_delay(self) -> float:
        return self.get_protection_delay("current")

    def set_power_protection_enabled(self, enabled: bool) -> None:
        self.set_protection_enabled("power", enabled)

    def is_power_protection_enabled(self) -> bool:
        return self.is_protection_enabled("power")

    def set_power_protection_level(self, watts: float) -> None:
        self.set_protection_level("power", watts)

    def get_power_protection_level(self) -> float:
        return self.get_protection_level("power")

    def set_power_protection_delay(self, seconds: float) -> None:
        self.set_protection_delay("power", seconds)

    def get_power_protection_delay(self) -> float:
        return self.get_protection_delay("power")

    def set_4wire_enabled(self, enabled: bool) -> None:
        self.write(f"SYST:SENS {_boolean_token(enabled)}")

    def is_4wire_enabled(self) -> bool:
        return self.query("SYST:SENS?") == "1"

    def set_turn_on_voltage(self, volts: float) -> None:
        self.write(f":SOUR:VOLT:LEV:ON {volts}")

    def get_turn_on_voltage(self) -> float:
        return float(self.query(":SOUR:VOLT:LEV:ON?"))

    def set_turn_on_voltage_latch_enabled(self, enabled: bool) -> None:
        self.write(f":SOUR:VOLT:LATCH:STAT {_boolean_token(enabled)}")

    def is_turn_on_voltage_latch_enabled(self) -> bool:
        return self.query(":SOUR:VOLT:LATCH:STAT?") == "1"

    def enter_battery_mode(self) -> None:
        self.write(":SOUR:BATT:FUNC")

    def is_battery_mode_enabled(self) -> bool:
        return self.query(":SOUR:BATT:FUNC?") == "1"

    def set_battery_mode(self, mode: BatteryModeLike) -> None:
        self.write(f":SOUR:BATT:MODE {_battery_mode_token(mode)}")

    def get_battery_mode(self) -> str:
        return self.query(":SOUR:BATT:MODE?")

    def set_battery_level(self, value: float) -> None:
        self.write(f":SOUR:BATT:LEV {value}")

    def get_battery_level(self) -> float:
        return float(self.query(":SOUR:BATT:LEV?"))

    def set_battery_cutoff_voltage(self, volts: float) -> None:
        self.write(f":SOUR:BATT:VOLT {volts}")

    def get_battery_cutoff_voltage(self) -> float:
        return float(self.query(":SOUR:BATT:VOLT?"))

    def set_battery_voltage_cutoff_enabled(self, enabled: bool) -> None:
        self.write(f":SOUR:BATT:VOLT:STAT {_boolean_token(enabled)}")

    def is_battery_voltage_cutoff_enabled(self) -> bool:
        return self.query(":SOUR:BATT:VOLT:STAT?") == "1"

    def set_battery_capability_cutoff(self, amp_hours: float) -> None:
        self.write(f":SOUR:BATT:CAP {amp_hours}")

    def get_battery_capability_cutoff(self) -> float:
        return float(self.query(":SOUR:BATT:CAP?"))

    def set_battery_capability_cutoff_enabled(self, enabled: bool) -> None:
        self.write(f":SOUR:BATT:CAP:STAT {_boolean_token(enabled)}")

    def is_battery_capability_cutoff_enabled(self) -> bool:
        return self.query(":SOUR:BATT:CAP:STAT?") == "1"

    def set_battery_timer_cutoff(self, seconds: float) -> None:
        self.write(f":SOUR:BATT:TIM {seconds}")

    def get_battery_timer_cutoff(self) -> float:
        return float(self.query(":SOUR:BATT:TIM?"))

    def set_battery_timer_cutoff_enabled(self, enabled: bool) -> None:
        self.write(f":SOUR:BATT:TIM:STAT {_boolean_token(enabled)}")

    def is_battery_timer_cutoff_enabled(self) -> bool:
        return self.query(":SOUR:BATT:TIM:STAT?") == "1"

    def set_battery_voltage_stop(self, volts: float) -> None:
        self.set_battery_cutoff_voltage(volts)

    def get_battery_voltage_stop(self) -> float:
        return self.get_battery_cutoff_voltage()

    def set_battery_voltage_stop_enabled(self, enabled: bool) -> None:
        self.set_battery_voltage_cutoff_enabled(enabled)

    def is_battery_voltage_stop_enabled(self) -> bool:
        return self.is_battery_voltage_cutoff_enabled()

    def set_battery_capacity_stop(self, amp_hours: float) -> None:
        self.set_battery_capability_cutoff(amp_hours)

    def get_battery_capacity_stop(self) -> float:
        return self.get_battery_capability_cutoff()

    def set_battery_capacity_stop_enabled(self, enabled: bool) -> None:
        self.set_battery_capability_cutoff_enabled(enabled)

    def is_battery_capacity_stop_enabled(self) -> bool:
        return self.is_battery_capability_cutoff_enabled()

    def set_battery_timer_stop(self, seconds: float) -> None:
        self.set_battery_timer_cutoff(seconds)

    def get_battery_timer_stop(self) -> float:
        return self.get_battery_timer_cutoff()

    def set_battery_timer_stop_enabled(self, enabled: bool) -> None:
        self.set_battery_timer_cutoff_enabled(enabled)

    def is_battery_timer_stop_enabled(self) -> bool:
        return self.is_battery_timer_cutoff_enabled()

    def configure_battery_stops(
        self,
        voltage_v: float | None = None,
        capacity_ah: float | None = None,
        timer_s: float | None = None,
    ) -> None:
        if voltage_v is None:
            self.set_battery_voltage_stop_enabled(False)
        else:
            self.set_battery_voltage_stop(voltage_v)
            self.set_battery_voltage_stop_enabled(True)

        if capacity_ah is None:
            self.set_battery_capacity_stop_enabled(False)
        else:
            self.set_battery_capacity_stop(capacity_ah)
            self.set_battery_capacity_stop_enabled(True)

        if timer_s is None:
            self.set_battery_timer_stop_enabled(False)
        else:
            self.set_battery_timer_stop(timer_s)
            self.set_battery_timer_stop_enabled(True)

    def get_battery_discharge_capacity(self) -> float:
        return float(self.query(":SOUR:BATT:DISCHArg:CAPability?"))

    def get_battery_discharge_time(self) -> float:
        return float(self.query(":SOUR:BATT:DISCHArg:TIMer?"))

    def set_battery_dcr_time1(self, seconds: float) -> None:
        self.write(f":SOUR:BATT:DCR:TIME1 {seconds}")

    def get_battery_dcr_time1(self) -> float:
        return float(self.query(":SOUR:BATT:DCR:TIME1?"))

    def set_battery_dcr_time2(self, seconds: float) -> None:
        self.write(f":SOUR:BATT:DCR:TIME2 {seconds}")

    def get_battery_dcr_time2(self) -> float:
        return float(self.query(":SOUR:BATT:DCR:TIME2?"))

    def set_battery_dcr_current1(self, amps: float) -> None:
        self.write(f":SOUR:BATT:DCR:CURR1 {amps}")

    def get_battery_dcr_current1(self) -> float:
        return float(self.query(":SOUR:BATT:DCR:CURR1?"))

    def set_battery_dcr_current2(self, amps: float) -> None:
        self.write(f":SOUR:BATT:DCR:CURR2 {amps}")

    def get_battery_dcr_current2(self) -> float:
        return float(self.query(":SOUR:BATT:DCR:CURR2?"))

    def configure_battery_dcr(
        self,
        current1_a: float,
        current2_a: float,
        time1_s: float,
        time2_s: float,
    ) -> None:
        self.set_battery_dcr_current1(current1_a)
        self.set_battery_dcr_current2(current2_a)
        self.set_battery_dcr_time1(time1_s)
        self.set_battery_dcr_time2(time2_s)

    def get_battery_dcr_result(self) -> float:
        return float(self.query(":SOUR:BATT:DCR:RESult?"))

    def measure_voltage(self) -> float:
        return float(self.query("MEAS:VOLT:DC?"))

    def measure_current(self) -> float:
        return float(self.query("MEAS:CURR:DC?"))

    def measure_power(self) -> float:
        return float(self.query("MEAS:POW:DC?"))

    def measure_resistance(self) -> float:
        return float(self.query("MEAS:RES:DC?"))

    def measure_waveform(self, metric: WaveformMetricLike) -> list[float]:
        values = self.query(f"MEAS:WAVEdata? {_siglent_mode_token(metric)}")
        return [float(value) for value in values.split(",") if value]

    def measure_all(self) -> Measurement:
        return Measurement(
            voltage_v=self.measure_voltage(),
            current_a=self.measure_current(),
            power_w=self.measure_power(),
        )

    def configure_list_mode(
        self,
        mode: TransientModeLike,
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

    def is_list_mode_enabled(self) -> bool:
        return self.query(":SOUR:LIST:STAT?") == "1"

    def set_trigger_source(self, source: TriggerSourceLike) -> None:
        self.write(f"TRIG:SOUR {_trigger_source_token(source)}")

    def get_trigger_source(self) -> str:
        return self.query("TRIG:SOUR?")

    def trigger(self) -> None:
        self.write("*TRG")

    def _ensure_open(self) -> None:
        if self._transport is None:
            raise InstrumentError("Siglent instrument transport is not open")
