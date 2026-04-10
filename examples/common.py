import csv
from datetime import datetime, timezone
import logging
from pathlib import Path
import time

from siglent_driver import InstrumentError, SiglentSDL1030, configure_logging
from pyvisa_py.usb import USBInstrSession


ROOT = Path(__file__).resolve().parents[1]
AUTO_USB_VISA_RESOURCE = "AUTO_USB_VISA"
USB_VISA_RESOURCE = "USB0::0xF4EC::0x1621::YOUR_SERIAL_HERE::INSTR"
LAN_VISA_RESOURCE = "TCPIP0::192.168.1.55::inst0::INSTR"
USBTMC_RESOURCE = "/dev/usbtmc0"
SIGLENT_USB_VENDOR_ID = 0xF4EC
SIGLENT_SDL1030_USB_PRODUCT_ID = 0x1621


def create_log_path(stem: str) -> Path:
    log_dir = ROOT / "log"
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return log_dir / f"{timestamp}_{stem}.csv"


def open_csv_writer(path: Path, fieldnames: list[str]) -> tuple[object, csv.DictWriter]:
    handle = path.open("w", newline="")
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    writer.writeheader()
    return handle, writer


def iso_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_sdl1030_usb_visa_resource(resource: str) -> bool:
    parts = resource.split("::")
    if len(parts) < 5:
        return False
    try:
        vendor_id = int(parts[1], 0)
        product_id = int(parts[2], 0)
    except ValueError:
        return False
    return (
        parts[0].startswith("USB")
        and vendor_id == SIGLENT_USB_VENDOR_ID
        and product_id == SIGLENT_SDL1030_USB_PRODUCT_ID
        and parts[-1] == "INSTR"
    )


def _iter_usbtmc_device_paths() -> list[Path]:
    return sorted(Path("/dev").glob("usbtmc*"))


def _read_sysfs_hex(path: Path) -> int | None:
    try:
        return int(path.read_text().strip(), 16)
    except (OSError, ValueError):
        return None


def _get_usbtmc_usb_ids(device_path: Path) -> tuple[int | None, int | None]:
    sysfs_roots = [
        Path("/sys/class/usbmisc") / device_path.name / "device",
        Path("/sys/class/usbtmc") / device_path.name / "device",
    ]
    sysfs_root = next((path for path in sysfs_roots if path.exists()), None)
    if sysfs_root is None:
        return None, None
    return (
        _read_sysfs_hex(sysfs_root / "idVendor"),
        _read_sysfs_hex(sysfs_root / "idProduct"),
    )


def find_usb_visa_resource(visa_backend: str | None) -> str:
    try:
        matches = [resource for resource in USBInstrSession.list_resources() if _is_sdl1030_usb_visa_resource(resource)]
    except Exception as exc:
        raise InstrumentError(
            "Failed to scan USB VISA resources. Set `CONNECTION['resource']` to the exact VISA string "
            "or use `/dev/usbtmc0`."
        ) from exc

    if not matches:
        raise InstrumentError(
            "No SDL1030 VISA USB resource was found. Set `CONNECTION['resource']` to the exact "
            "VISA string or use `/dev/usbtmc0`."
        )

    if len(matches) > 1:
        formatted = ", ".join(matches)
        raise InstrumentError(
            f"Multiple SDL1030 VISA USB resources were found: {formatted}. "
            "Set `CONNECTION['resource']` explicitly."
        )

    return matches[0]


def find_usbtmc_resource() -> str:
    device_paths = _iter_usbtmc_device_paths()
    matched_paths: list[str] = []
    unknown_identity_paths: list[str] = []

    for device_path in device_paths:
        vendor_id, product_id = _get_usbtmc_usb_ids(device_path)
        if vendor_id is None or product_id is None:
            unknown_identity_paths.append(str(device_path))
            continue
        if vendor_id == SIGLENT_USB_VENDOR_ID and product_id == SIGLENT_SDL1030_USB_PRODUCT_ID:
            matched_paths.append(str(device_path))

    if len(matched_paths) == 1:
        return matched_paths[0]

    if len(matched_paths) > 1:
        formatted = ", ".join(matched_paths)
        raise InstrumentError(
            f"Multiple SDL1030 Linux USBTMC devices were found: {formatted}. "
            "Set `CONNECTION['resource']` explicitly."
        )

    if len(device_paths) == 1 and len(unknown_identity_paths) == 1:
        return unknown_identity_paths[0]

    raise InstrumentError(
        "No SDL1030 Linux USBTMC device was found. Set `CONNECTION['resource']` to the exact "
        "device path such as `/dev/usbtmc0`."
    )


def find_usb_resource(visa_backend: str | None) -> str:
    try:
        return find_usb_visa_resource(visa_backend)
    except InstrumentError as visa_exc:
        if "Multiple SDL1030 VISA USB resources were found" in str(visa_exc):
            raise
        try:
            return find_usbtmc_resource()
        except InstrumentError as usbtmc_exc:
            raise InstrumentError(
                "No SDL1030 USB resource was found via VISA-over-USB or Linux USBTMC. Set "
                "`CONNECTION['resource']` to the exact VISA string or device path like `/dev/usbtmc0`."
            ) from usbtmc_exc


def connect_from_config(connection: dict[str, object]) -> SiglentSDL1030:
    configure_logging(logging.INFO)
    visa_backend = connection.get("visa_backend") if isinstance(connection.get("visa_backend"), str) else None
    resource = str(connection["resource"])
    if resource == AUTO_USB_VISA_RESOURCE:
        resource = find_usb_resource(visa_backend)

    return SiglentSDL1030(
        resource,
        timeout_ms=int(connection.get("timeout_ms", 3000)),
        visa_backend=visa_backend,
    )


def apply_common_settings(load: SiglentSDL1030, options: dict[str, object]) -> None:
    load.set_4wire_enabled(bool(options.get("enable_4wire", False)))

    turn_on_voltage_v = options.get("turn_on_voltage_v")
    if isinstance(turn_on_voltage_v, (int, float)):
        load.set_turn_on_voltage(float(turn_on_voltage_v))

    if "turn_on_voltage_latch_enabled" in options:
        load.set_turn_on_voltage_latch_enabled(bool(options.get("turn_on_voltage_latch_enabled", False)))

    if "current_protection_enabled" in options:
        load.set_current_protection_enabled(bool(options.get("current_protection_enabled", False)))
    current_protection_a = options.get("current_protection_a")
    if isinstance(current_protection_a, (int, float)):
        load.set_current_protection_level(float(current_protection_a))
    current_protection_delay_s = options.get("current_protection_delay_s")
    if isinstance(current_protection_delay_s, (int, float)):
        load.set_current_protection_delay(float(current_protection_delay_s))

    if "power_protection_enabled" in options:
        load.set_power_protection_enabled(bool(options.get("power_protection_enabled", False)))
    power_protection_w = options.get("power_protection_w")
    if isinstance(power_protection_w, (int, float)):
        load.set_power_protection_level(float(power_protection_w))
    power_protection_delay_s = options.get("power_protection_delay_s")
    if isinstance(power_protection_delay_s, (int, float)):
        load.set_power_protection_delay(float(power_protection_delay_s))


def measurement_row(
    elapsed_s: float,
    sample_index: int,
    step_name: str,
    load: SiglentSDL1030,
) -> dict[str, object]:
    measurement = load.measure_all()
    return {
        "timestamp_utc": iso_timestamp(),
        "elapsed_s": round(elapsed_s, 3),
        "sample_index": sample_index,
        "step_name": step_name,
        "voltage_V": measurement.voltage_v,
        "current_A": measurement.current_a,
        "power_W": measurement.power_w,
    }


def append_discharge_capacity(row: dict[str, object], load: SiglentSDL1030, enabled: bool) -> bool:
    if not enabled:
        row["discharge_capacity_mAh"] = ""
        return False
    try:
        row["discharge_capacity_mAh"] = load.get_battery_discharge_capacity() * 1000.0
        return True
    except InstrumentError as exc:
        logging.getLogger(__name__).warning(
            "Skipping discharge capacity logging because the instrument did not answer the query: %s",
            exc,
        )
        row["discharge_capacity_mAh"] = ""
        return False


def sleep_until_next_sample(interval_s: float) -> None:
    time.sleep(interval_s)
