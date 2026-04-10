#!/usr/bin/env python3
"""Run the battery/DCIR workflow and log the full trace to CSV.

Edit `CONNECTION` to choose USBTMC, VISA-over-USB, or VISA-over-LAN.
Edit `RUN` to change 4-wire sense, I/V range, OCP/OPP, timing, current levels,
and stop conditions.

Note: on the tested SDL1030X firmware, the DCIR result may stay at `0.0`.
This example still logs the full battery test trace for inspection.
"""

import time

from siglent_driver import BatteryMode, CurrentRange, VoltageRange

from common import (
    AUTO_USB_VISA_RESOURCE,
    LAN_VISA_RESOURCE,
    USB_VISA_RESOURCE,
    USBTMC_RESOURCE,
    apply_common_settings,
    connect_from_config,
    create_log_path,
    iso_timestamp,
    measurement_row,
    open_csv_writer,
    sleep_until_next_sample,
)


CONNECTION = {
    "resource": AUTO_USB_VISA_RESOURCE,
    # Alternative examples:
    # "resource": USB_VISA_RESOURCE,
    # "resource": LAN_VISA_RESOURCE,
    # "resource": USBTMC_RESOURCE,
    "visa_backend": "@py",
    "timeout_ms": 3000,
}

RUN = {
    "enable_4wire": True,
    "battery_mode": BatteryMode.CC,
    "current_range": CurrentRange.A5,
    "voltage_range": VoltageRange.V36,
    "current_protection_enabled": False,
    "current_protection_a": 2.0,
    "current_protection_delay_s": 0.1,
    "power_protection_enabled": False,
    "power_protection_w": 100.0,
    "power_protection_delay_s": 0.1,
    # This is the documented turn-on voltage / latch setting, not a separate OVP command.
    "turn_on_voltage_v": None,
    "turn_on_voltage_latch_enabled": False,
    "current1_a": 0.1,
    "current2_a": 0.2,
    "time1_s": 1.0,
    "time2_s": 1.0,
    "sample_interval_s": 0.25,
    # On the tested firmware the active battery current followed BATT:LEV.
    "battery_level_a": 0.1,
    "timer_cutoff_s": 4.0,
}


def main() -> int:
    csv_path = create_log_path("dcir_battery_test")
    with connect_from_config(CONNECTION) as load:
        handle, writer = open_csv_writer(
            csv_path,
            [
                "timestamp_utc",
                "elapsed_s",
                "sample_index",
                "step_name",
                "voltage_v",
                "current_a",
                "power_w",
                "dcir_ohm",
            ],
        )
        apply_common_settings(load, RUN)
        load.enter_battery_mode()
        load.set_battery_mode(RUN["battery_mode"])
        load.set_current_range("battery", RUN["current_range"])
        load.set_voltage_range("battery", RUN["voltage_range"])
        load.set_battery_level(float(RUN["battery_level_a"]))
        load.configure_battery_stops(
            voltage_v=None,
            capacity_ah=None,
            timer_s=float(RUN["timer_cutoff_s"]),
        )
        load.configure_battery_dcr(
            current1_a=float(RUN["current1_a"]),
            current2_a=float(RUN["current2_a"]),
            time1_s=float(RUN["time1_s"]),
            time2_s=float(RUN["time2_s"]),
        )

        load.set_input_enabled(True)
        started = time.monotonic()
        sample_index = 0
        total_duration_s = float(RUN["timer_cutoff_s"]) + 1.0
        try:
            while time.monotonic() - started < total_duration_s:
                row = measurement_row(
                    elapsed_s=time.monotonic() - started,
                    sample_index=sample_index,
                    step_name="battery_dcir",
                    load=load,
                )
                row["dcir_ohm"] = round(load.get_battery_dcr_result(), 6)
                writer.writerow(row)
                handle.flush()
                sample_index += 1
                sleep_until_next_sample(float(RUN["sample_interval_s"]))
                if not load.is_input_enabled():
                    break
        finally:
            load.set_input_enabled(False)

        final_dcir = load.get_battery_dcr_result()
        writer.writerow(
            {
                "timestamp_utc": iso_timestamp(),
                "elapsed_s": round(time.monotonic() - started, 3),
                "sample_index": sample_index,
                "step_name": "dcir_result",
                "voltage_v": "",
                "current_a": "",
                "power_w": "",
                "dcir_ohm": round(final_dcir, 6),
            }
        )
        handle.close()

    print(f"Wrote DCIR log to {csv_path}")
    if final_dcir <= 0.0:
        print("DCIR result stayed at 0.0 on this firmware. The CSV still contains the battery test trace.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
