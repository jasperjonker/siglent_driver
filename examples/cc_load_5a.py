#!/usr/bin/env python3
"""Run the SDL1030X at 5 A and let the load stop itself at 26 V.

Edit `CONNECTION` to choose USBTMC, VISA-over-USB, or VISA-over-LAN.
Edit `RUN` to change 4-wire sense, range, OCP/OPP, turn-on voltage behavior,
the built-in V_STOP / C_STOP / T_STOP values, current, or sample interval.

This uses the SDL battery CC mode so the instrument can enforce the stop
conditions internally instead of relying on script-side cutoff logic.
"""

import time

from siglent_driver import BatteryMode, CurrentRange, VoltageRange

from common import (
    AUTO_USB_VISA_RESOURCE,
    LAN_VISA_RESOURCE,
    USB_VISA_RESOURCE,
    USBTMC_RESOURCE,
    append_discharge_capacity,
    apply_common_settings,
    connect_from_config,
    create_log_path,
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
    "current_protection_a": 8.0,
    "current_protection_delay_s": 0.1,
    "power_protection_enabled": False,
    "power_protection_w": 300.0,
    "power_protection_delay_s": 0.1,
    # This is the documented turn-on voltage / latch setting, not a separate OVP command.
    "turn_on_voltage_v": None,
    "turn_on_voltage_latch_enabled": False,
    "voltage_stop_v": 26.0,
    "capacity_stop_ah": None,
    "timer_stop_s": None,
    "current_a": 5.0,
    "sample_interval_s": 1.0,
    "max_duration_s": 7200.0,
}


def main() -> int:
    csv_path = create_log_path("cc_load_5a")
    with connect_from_config(CONNECTION) as load:
        handle, writer = open_csv_writer(
            csv_path,
            [
                "timestamp_utc",
                "elapsed_s",
                "sample_index",
                "step_name",
                "voltage_V",
                "current_A",
                "power_W",
                "discharge_capacity_mAh",
            ],
        )
        apply_common_settings(load, RUN)
        load.enter_battery_mode()
        load.set_battery_mode(RUN["battery_mode"])
        load.set_current_range("battery", RUN["current_range"])
        load.set_voltage_range("battery", RUN["voltage_range"])
        load.set_battery_level(float(RUN["current_a"]))
        load.configure_battery_stops(
            voltage_v=RUN["voltage_stop_v"],
            capacity_ah=RUN["capacity_stop_ah"],
            timer_s=RUN["timer_stop_s"],
        )
        load.set_input_enabled(True)

        started = time.monotonic()
        discharge_capacity_enabled = True
        try:
            sample_index = 0
            while time.monotonic() - started < float(RUN["max_duration_s"]):
                row = measurement_row(
                    elapsed_s=time.monotonic() - started,
                    sample_index=sample_index,
                    step_name="battery_cc_5a",
                    load=load,
                )
                discharge_capacity_enabled = append_discharge_capacity(
                    row,
                    load,
                    discharge_capacity_enabled,
                )
                writer.writerow(row)
                handle.flush()
                sample_index += 1
                if not load.is_input_enabled():
                    break
                sleep_until_next_sample(float(RUN["sample_interval_s"]))
        finally:
            load.set_input_enabled(False)
            handle.close()

    print(f"Wrote 5 A stop-test log to {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
