import logging

from siglent_driver import Measurement, configure_logging
from siglent_driver.siglent import (
    CURRENT_RANGE_VALUES,
    VOLTAGE_RANGE_VALUES,
    BatteryMode,
    CurrentRange,
    LoadMode,
    ResistanceRange,
    SiglentSDL1030,
    TransientMode,
    TransientWaveform,
    TriggerSource,
    VoltageRange,
    _canonical_current_range,
    _canonical_voltage_range,
    _siglent_mode_token,
)


class FakeTransport:
    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.responses = responses or {}
        self.commands: list[tuple[str, str]] = []

    def write(self, command: str) -> None:
        self.commands.append(("write", command))

    def query(self, command: str) -> str:
        self.commands.append(("query", command))
        return self.responses[command]

    def close(self) -> None:
        self.commands.append(("close", ""))


def make_load(responses: dict[str, str] | None = None) -> tuple[SiglentSDL1030, FakeTransport]:
    load = SiglentSDL1030("test")
    transport = FakeTransport(responses)
    load._transport = transport
    return load, transport


def test_mode_token_mapping() -> None:
    assert _siglent_mode_token("current") == "CURRent"
    assert _siglent_mode_token(LoadMode.CV) == "VOLTage"
    assert _siglent_mode_token(TransientMode.CP) == "POWer"
    assert _siglent_mode_token(BatteryMode.CR) == "RESistance"
    assert _siglent_mode_token(LoadMode.LED) == "LED"


def test_measurement_to_dict() -> None:
    measurement = Measurement(voltage_v=12.3, current_a=0.45, power_w=5.535)
    assert measurement.to_dict() == {
        "voltage_v": 12.3,
        "current_a": 0.45,
        "power_w": 5.535,
    }


def test_range_normalization_matches_supported_ranges() -> None:
    assert _canonical_current_range(0.1) is CurrentRange.A5
    assert _canonical_current_range(CurrentRange.A5) is CurrentRange.A5
    assert _canonical_current_range(5.1) is CurrentRange.A30
    assert _canonical_voltage_range(12.0) is VoltageRange.V36
    assert _canonical_voltage_range(VoltageRange.V36) is VoltageRange.V36
    assert _canonical_voltage_range(36.1) is VoltageRange.V150
    assert CURRENT_RANGE_VALUES == (5.0, 30.0)
    assert VOLTAGE_RANGE_VALUES == (36.0, 150.0)


def test_range_and_sense_commands() -> None:
    load, transport = make_load()

    load.set_current_range("current", CurrentRange.A5)
    load.set_current_range("battery", 9.0)
    load.set_voltage_range("current", VoltageRange.V36)
    load.set_voltage_range("power", 72.0)
    load.set_resistance_range("resistance", ResistanceRange.UPPER)
    load.set_4wire_enabled(True)
    load.set_4wire_enabled(False)

    assert transport.commands == [
        ("write", ":SOUR:CURRent:IRANG 5.0"),
        ("write", ":SOUR:BATTery:IRANG 30.0"),
        ("write", ":SOUR:CURRent:VRANG 36.0"),
        ("write", ":SOUR:POWer:VRANG 150.0"),
        ("write", ":SOUR:RESistance:RRANG UPPER"),
        ("write", "SYST:SENS ON"),
        ("write", "SYST:SENS OFF"),
    ]


def test_transient_configuration_commands() -> None:
    load, transport = make_load()

    load.configure_transient(
        mode=TransientMode.CC,
        waveform=TransientWaveform.TOGGLE,
        a_level=0.05,
        b_level=0.1,
        a_width_s=0.2,
        b_width_s=0.3,
    )
    load.set_current_transient_slew_positive(0.4)
    load.set_current_transient_slew_negative(0.3)

    assert transport.commands == [
        ("write", ":SOUR:FUNC:TRAN CURRent"),
        ("write", ":SOUR:CURRent:TRANsient:MODE TOGGle"),
        ("write", ":SOUR:CURRent:TRANsient:ALEV 0.05"),
        ("write", ":SOUR:CURRent:TRANsient:BLEV 0.1"),
        ("write", ":SOUR:CURRent:TRANsient:AWID 0.2"),
        ("write", ":SOUR:CURRent:TRANsient:BWID 0.3"),
        ("write", ":SOUR:CURRent:TRANsient:SLEW:POS 0.4"),
        ("write", ":SOUR:CURRent:TRANsient:SLEW:NEG 0.3"),
    ]


def test_protection_and_battery_dcr_commands() -> None:
    load, transport = make_load()

    load.set_current_protection_enabled(True)
    load.set_current_protection_level(0.25)
    load.set_current_protection_delay(0.1)
    load.set_power_protection_enabled(True)
    load.set_power_protection_level(8.0)
    load.set_power_protection_delay(0.2)
    load.enter_battery_mode()
    load.set_battery_mode(BatteryMode.CC)
    load.set_battery_level(0.1)
    load.configure_battery_stops(voltage_v=30.0, capacity_ah=None, timer_s=120.0)
    load.configure_battery_dcr(current1_a=0.1, current2_a=0.2, time1_s=1.0, time2_s=1.5)

    assert transport.commands == [
        ("write", ":SOUR:CURRent:PROTection:STAT ON"),
        ("write", ":SOUR:CURRent:PROTection:LEV 0.25"),
        ("write", ":SOUR:CURRent:PROTection:DEL 0.1"),
        ("write", ":SOUR:POWer:PROTection:STAT ON"),
        ("write", ":SOUR:POWer:PROTection:LEV 8.0"),
        ("write", ":SOUR:POWer:PROTection:DEL 0.2"),
        ("write", ":SOUR:BATT:FUNC"),
        ("write", ":SOUR:BATT:MODE CURRent"),
        ("write", ":SOUR:BATT:LEV 0.1"),
        ("write", ":SOUR:BATT:VOLT 30.0"),
        ("write", ":SOUR:BATT:VOLT:STAT ON"),
        ("write", ":SOUR:BATT:CAP:STAT OFF"),
        ("write", ":SOUR:BATT:TIM 120.0"),
        ("write", ":SOUR:BATT:TIM:STAT ON"),
        ("write", ":SOUR:BATT:DCR:CURR1 0.1"),
        ("write", ":SOUR:BATT:DCR:CURR2 0.2"),
        ("write", ":SOUR:BATT:DCR:TIME1 1.0"),
        ("write", ":SOUR:BATT:DCR:TIME2 1.5"),
    ]


def test_query_methods_parse_responses() -> None:
    load, transport = make_load(
        {
            ":SOUR:CURRent:IRANG?": "5",
            ":SOUR:POWer:VRANG?": "150",
            "SYST:SENS?": "1",
            ":SOUR:CURRent:PROTection:STAT?": "0",
            ":SOUR:BATT:DCR:RESult?": "0.082",
            "MEAS:WAVEdata? CURRent": "0.1,0.2,0.3",
        }
    )

    assert load.get_current_range("current") == 5.0
    assert load.get_voltage_range("power") == 150.0
    assert load.is_4wire_enabled() is True
    assert load.is_current_protection_enabled() is False
    assert load.get_battery_dcr_result() == 0.082
    assert load.measure_waveform("current") == [0.1, 0.2, 0.3]
    assert transport.commands == [
        ("query", ":SOUR:CURRent:IRANG?"),
        ("query", ":SOUR:POWer:VRANG?"),
        ("query", "SYST:SENS?"),
        ("query", ":SOUR:CURRent:PROTection:STAT?"),
        ("query", ":SOUR:BATT:DCR:RESult?"),
        ("query", "MEAS:WAVEdata? CURRent"),
    ]


def test_trigger_source_enum_command() -> None:
    load, transport = make_load()

    load.set_trigger_source(TriggerSource.BUS)

    assert transport.commands == [("write", "TRIG:SOUR BUS")]


def test_context_manager_opens_and_closes(monkeypatch) -> None:
    load = SiglentSDL1030("test")
    calls: list[str] = []

    monkeypatch.setattr(SiglentSDL1030, "open", lambda self: calls.append("open"))
    monkeypatch.setattr(SiglentSDL1030, "close", lambda self: calls.append("close"))

    with load as entered:
        assert entered is load

    assert calls == ["open", "close"]


def test_configure_logging_is_idempotent() -> None:
    logger_name = "siglent_driver.tests.logging"
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.propagate = True

    configured = configure_logging(logging.DEBUG, logger_name=logger_name)
    configured_again = configure_logging(logging.INFO, logger_name=logger_name)

    handlers = [entry for entry in configured.handlers if getattr(entry, "_siglent_driver_handler", False)]

    assert configured is configured_again
    assert len(handlers) == 1
    assert configured.level == logging.INFO
    assert configured.propagate is False
