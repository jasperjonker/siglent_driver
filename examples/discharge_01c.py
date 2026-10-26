#!/usr/bin/env python3
"""Run one pack at 0.1C on one SDL1030; run another process for another load."""

import argparse
import csv
import math
import time
from uuid import uuid4

from siglent_driver import BatteryMode, InstrumentError

from common import (
    AUTO_USB_VISA_RESOURCE,
    apply_battery_test_settings,
    connect_from_config,
    create_log_path,
    iso_timestamp,
    resolve_current_range,
    resolve_voltage_range,
    sanitize_filename_fragment,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True, help="Pack identifier used in log filenames")
    parser.add_argument("--capacity-ah", type=float, required=True, help="Rated pack capacity in Ah")
    parser.add_argument("--cutoff-v", type=float, required=True, help="Pack-level voltage cutoff in V")
    parser.add_argument("--resource", default=AUTO_USB_VISA_RESOURCE, help="Exact VISA resource or /dev/usbtmc path; required when multiple loads are connected")
    parser.add_argument("--four-wire", action="store_true", help="Use connected Kelvin sense leads")
    parser.add_argument("--sample-interval-s", type=float, default=5.0)
    parser.add_argument("--max-duration-s", type=float, default=12 * 3600.0)
    args = parser.parse_args()
    args.serial = sanitize_filename_fragment(args.serial)
    if not all(math.isfinite(v) and v > 0 for v in (args.capacity_ah, args.cutoff_v, args.sample_interval_s, args.max_duration_s)):
        parser.error("Capacity, cutoff voltage, sample interval, and maximum duration must be positive finite numbers.")
    if args.capacity_ah / 10 > 30 or args.cutoff_v > 150:
        parser.error("0.1C current must be at most 30 A and cutoff voltage at most 150 V for the SDL1030.")
    return args


def optional_battery_result(query) -> float | str:
    try:
        return query()
    except InstrumentError:
        return ""


def run(args: argparse.Namespace) -> tuple[object, object]:
    current = args.capacity_ah / 10.0
    connection = {"resource": args.resource, "visa_backend": "@py", "timeout_ms": 3000}
    # The random run ID also prevents two laptop processes from choosing the same log path.
    csv_path = create_log_path(f"discharge_01c_{uuid4().hex[:8]}", battery_serial=args.serial)
    summary_path = csv_path.with_name(f"{csv_path.stem}_summary.csv")
    fields = ["timestamp_utc", "elapsed_s", "voltage_V", "current_A", "power_W", "capacity_Ah", "energy_Wh"]

    with connect_from_config(connection) as load:
        if load.is_input_enabled():
            raise RuntimeError("Selected load input is already ON. Use a different instrument resource or stop its existing run first.")
        load.set_4wire_enabled(args.four_wire)
        initial_voltage = load.measure_voltage()
        if initial_voltage <= args.cutoff_v or initial_voltage > 150:
            raise ValueError(f"Measured pack voltage {initial_voltage:g} V must be above cutoff {args.cutoff_v:g} V and at most 150 V.")

        load.enter_battery_mode()
        load.set_battery_mode(BatteryMode.CC)
        apply_battery_test_settings(load, {"enable_4wire": args.four_wire, "voltage_stop_v": args.cutoff_v})
        load.set_current_range("battery", resolve_current_range(None, current))
        load.set_voltage_range("battery", resolve_voltage_range(load, None, initial_voltage))
        load.set_battery_level(current)
        if not load.is_battery_voltage_stop_enabled() or not math.isclose(load.get_battery_voltage_stop(), args.cutoff_v, abs_tol=0.01):
            raise RuntimeError("Instrument voltage cutoff readback does not match the requested value.")

        print(f"{args.serial}: {initial_voltage:g} V, {current:g} A (0.1C), cutoff {args.cutoff_v:g} V on {args.resource}")
        input("Confirm pack connection and press Enter to start discharge. ")
        if load.is_input_enabled():
            raise RuntimeError("Selected load input turned ON before this run started.")

        capacity_ah = energy_wh = 0.0
        last = None
        stop = "maximum duration"
        started = time.monotonic()
        with csv_path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            try:
                load.set_input_enabled(True)
                while time.monotonic() - started < args.max_duration_s:
                    if not load.is_input_enabled():
                        stop = "instrument stopped (voltage cutoff or another condition)"
                        break
                    sample = load.measure_all()
                    elapsed = time.monotonic() - started
                    if last is not None:
                        hours = (elapsed - last[0]) / 3600.0
                        capacity_ah += (last[1].current_a + sample.current_a) * hours / 2
                        energy_wh += (last[1].power_w + sample.power_w) * hours / 2
                    writer.writerow({
                        "timestamp_utc": iso_timestamp(), "elapsed_s": round(elapsed, 3),
                        "voltage_V": sample.voltage_v, "current_A": sample.current_a,
                        "power_W": sample.power_w, "capacity_Ah": round(capacity_ah, 6),
                        "energy_Wh": round(energy_wh, 6),
                    })
                    handle.flush()
                    last = (elapsed, sample)
                    time.sleep(args.sample_interval_s)
            finally:
                load.set_input_enabled(False)

        summary = {
            "serial": args.serial, "resource": args.resource, "rated_capacity_Ah": args.capacity_ah,
            "set_current_A": current, "cutoff_voltage_V": args.cutoff_v,
            "initial_voltage_V": initial_voltage, "last_loaded_voltage_V": last[1].voltage_v if last else "",
            "elapsed_s": round(time.monotonic() - started, 3),
            "capacity_Ah": round(capacity_ah, 6), "energy_Wh": round(energy_wh, 6),
            "instrument_capacity_Ah": optional_battery_result(load.get_battery_discharge_capacity),
            "instrument_time_s": optional_battery_result(load.get_battery_discharge_time),
            "stop": stop, "sample_csv": str(csv_path),
        }

    with summary_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary))
        writer.writeheader()
        writer.writerow(summary)
    print(f"{stop}: {capacity_ah:.3f} Ah, {energy_wh:.3f} Wh. Logs: {csv_path}, {summary_path}")
    return csv_path, summary_path


if __name__ == "__main__":
    run(parse_args())
