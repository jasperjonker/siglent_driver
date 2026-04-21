from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from siglent_driver import InstrumentError


COMMON_PATH = Path(__file__).resolve().parents[1] / "examples" / "common.py"
COMMON_SPEC = spec_from_file_location("examples_common", COMMON_PATH)
assert COMMON_SPEC is not None
assert COMMON_SPEC.loader is not None
common = module_from_spec(COMMON_SPEC)
COMMON_SPEC.loader.exec_module(common)


class FakeLoad:
    def __init__(
        self,
        capacity: float | None = None,
        exc: Exception | None = None,
        measured_voltage: float | None = None,
        voltage_exc: Exception | None = None,
    ) -> None:
        self.capacity = capacity
        self.exc = exc
        self.measured_voltage = measured_voltage
        self.voltage_exc = voltage_exc

    def get_battery_discharge_capacity(self) -> float:
        if self.exc is not None:
            raise self.exc
        assert self.capacity is not None
        return self.capacity

    def measure_voltage(self) -> float:
        if self.voltage_exc is not None:
            raise self.voltage_exc
        assert self.measured_voltage is not None
        return self.measured_voltage


class RecorderLoad:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def set_4wire_enabled(self, enabled: bool) -> None:
        self.calls.append(("set_4wire_enabled", enabled))

    def set_turn_on_voltage(self, volts: float) -> None:
        self.calls.append(("set_turn_on_voltage", volts))

    def set_turn_on_voltage_latch_enabled(self, enabled: bool) -> None:
        self.calls.append(("set_turn_on_voltage_latch_enabled", enabled))

    def configure_battery_stops(
        self,
        voltage_v: float | None = None,
        capacity_ah: float | None = None,
        timer_s: float | None = None,
    ) -> None:
        self.calls.append(("configure_battery_stops", (voltage_v, capacity_ah, timer_s)))


def test_usb_visa_resource_match_accepts_pyvisa_py_format() -> None:
    assert common._is_sdl1030_usb_visa_resource("USB0::0xF4EC::0x1621::SDL123456::0::INSTR") is True
    assert common._is_sdl1030_usb_visa_resource("USB0::0xF4EC::0x1621::SDL123456::INSTR") is True
    assert common._is_sdl1030_usb_visa_resource("USB0::0x1234::0x1621::SDL123456::0::INSTR") is False


def test_find_usb_resource_prefers_visa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(common, "find_usb_visa_resource", lambda backend: "USB0::0xF4EC::0x1621::SDL123456::0::INSTR")
    monkeypatch.setattr(common, "find_usbtmc_resource", lambda: "/dev/usbtmc0")

    assert common.find_usb_resource("@py") == "USB0::0xF4EC::0x1621::SDL123456::0::INSTR"


def test_find_usb_resource_falls_back_to_usbtmc(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_no_visa(backend: str | None) -> str:
        raise InstrumentError("No SDL1030 VISA USB resource was found.")

    monkeypatch.setattr(common, "find_usb_visa_resource", raise_no_visa)
    monkeypatch.setattr(common, "find_usbtmc_resource", lambda: "/dev/usbtmc0")

    assert common.find_usb_resource("@py") == "/dev/usbtmc0"


def test_find_usb_resource_preserves_multiple_visa_match_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_multiple_visa(backend: str | None) -> str:
        raise InstrumentError("Multiple SDL1030 VISA USB resources were found: A, B.")

    monkeypatch.setattr(common, "find_usb_visa_resource", raise_multiple_visa)
    monkeypatch.setattr(common, "find_usbtmc_resource", lambda: "/dev/usbtmc0")

    with pytest.raises(InstrumentError, match="Multiple SDL1030 VISA USB resources were found"):
        common.find_usb_resource("@py")


def test_find_usbtmc_resource_returns_single_matching_device(monkeypatch: pytest.MonkeyPatch) -> None:
    paths = [Path("/dev/usbtmc0"), Path("/dev/usbtmc1")]

    monkeypatch.setattr(common, "_iter_usbtmc_device_paths", lambda: paths)

    def fake_usb_ids(path: Path) -> tuple[int | None, int | None]:
        if path.name == "usbtmc0":
            return common.SIGLENT_USB_VENDOR_ID, common.SIGLENT_SDL1030_USB_PRODUCT_ID
        return 0x1111, 0x2222

    monkeypatch.setattr(common, "_get_usbtmc_usb_ids", fake_usb_ids)

    assert common.find_usbtmc_resource() == "/dev/usbtmc0"


def test_find_usbtmc_resource_uses_single_unknown_device(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(common, "_iter_usbtmc_device_paths", lambda: [Path("/dev/usbtmc0")])
    monkeypatch.setattr(common, "_get_usbtmc_usb_ids", lambda path: (None, None))

    assert common.find_usbtmc_resource() == "/dev/usbtmc0"


def test_find_usbtmc_resource_raises_for_multiple_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(common, "_iter_usbtmc_device_paths", lambda: [Path("/dev/usbtmc0"), Path("/dev/usbtmc1")])
    monkeypatch.setattr(
        common,
        "_get_usbtmc_usb_ids",
        lambda path: (common.SIGLENT_USB_VENDOR_ID, common.SIGLENT_SDL1030_USB_PRODUCT_ID),
    )

    with pytest.raises(InstrumentError, match="Multiple SDL1030 Linux USBTMC devices were found"):
        common.find_usbtmc_resource()


def test_find_usb_resource_raises_when_no_usb_transport_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(common, "find_usb_visa_resource", lambda backend: (_ for _ in ()).throw(InstrumentError("no visa")))
    monkeypatch.setattr(common, "find_usbtmc_resource", lambda: (_ for _ in ()).throw(InstrumentError("no usbtmc")))

    with pytest.raises(InstrumentError, match="No SDL1030 USB resource was found via VISA-over-USB or Linux USBTMC"):
        common.find_usb_resource("@py")


def test_append_discharge_capacity_records_value() -> None:
    row: dict[str, object] = {}

    enabled = common.append_discharge_capacity(row, FakeLoad(capacity=0.123), True)

    assert enabled is True
    assert row["discharge_capacity_mAh"] == 123.0


def test_append_discharge_capacity_disables_on_query_error(caplog: pytest.LogCaptureFixture) -> None:
    row: dict[str, object] = {}

    with caplog.at_level("WARNING"):
        enabled = common.append_discharge_capacity(row, FakeLoad(exc=InstrumentError("timeout")), True)

    assert enabled is False
    assert row["discharge_capacity_mAh"] == ""
    assert "Skipping discharge capacity logging" in caplog.text


def test_resolve_current_range_uses_explicit_value() -> None:
    assert common.resolve_current_range(30.0, 2.0, 4.0) == 30.0


def test_resolve_current_range_uses_max_candidate_for_auto() -> None:
    assert common.resolve_current_range(common.AUTO_RANGE, 2.0, 5.1, 4.0) == 5.1
    assert common.resolve_current_range(None, 2.0, -8.0, 4.0) == 8.0


def test_resolve_voltage_range_uses_measured_input_voltage_for_auto() -> None:
    load = FakeLoad(measured_voltage=48.2)

    assert common.resolve_voltage_range(load, common.AUTO_RANGE, 26.0, None) == 48.2


def test_resolve_voltage_range_falls_back_to_configured_candidates() -> None:
    load = FakeLoad(voltage_exc=InstrumentError("measure failed"))

    assert common.resolve_voltage_range(load, None, 26.0, 54.0) == 54.0


def test_resolve_voltage_range_uses_explicit_value() -> None:
    load = FakeLoad(measured_voltage=48.2)

    assert common.resolve_voltage_range(load, 36.0, 54.0) == 36.0


def test_apply_battery_test_settings_uses_battery_stop_configuration() -> None:
    load = RecorderLoad()

    common.apply_battery_test_settings(
        load,
        {
            "enable_4wire": True,
            "turn_on_voltage_v": 10.5,
            "turn_on_voltage_latch_enabled": True,
            "voltage_stop_v": 26.0,
            "capacity_stop_ah": 1.5,
            "timer_stop_s": 120.0,
        },
    )

    assert load.calls == [
        ("set_4wire_enabled", True),
        ("set_turn_on_voltage", 10.5),
        ("set_turn_on_voltage_latch_enabled", True),
        ("configure_battery_stops", (26.0, 1.5, 120.0)),
    ]
