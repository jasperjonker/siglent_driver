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
    def __init__(self, capacity: float | None = None, exc: Exception | None = None) -> None:
        self.capacity = capacity
        self.exc = exc

    def get_battery_discharge_capacity(self) -> float:
        if self.exc is not None:
            raise self.exc
        assert self.capacity is not None
        return self.capacity


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
    assert row["discharge_capacity"] == 0.123


def test_append_discharge_capacity_disables_on_query_error(caplog: pytest.LogCaptureFixture) -> None:
    row: dict[str, object] = {}

    with caplog.at_level("WARNING"):
        enabled = common.append_discharge_capacity(row, FakeLoad(exc=InstrumentError("timeout")), True)

    assert enabled is False
    assert row["discharge_capacity"] == ""
    assert "Skipping discharge capacity logging" in caplog.text
