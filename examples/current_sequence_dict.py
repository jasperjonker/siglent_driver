#!/usr/bin/env python3
"""Run a simple dict-driven CC current sequence and log it to CSV.

Edit `CONNECTION` to choose USBTMC, VISA-over-USB, or VISA-over-LAN.
Edit `RUN` to change 4-wire sense, range, OCP/OPP, turn-on voltage behavior,
sample interval, or the step list.
"""

import time

from siglent_driver import LoadMode

from common import (
    AUTO_RANGE,
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
    resolve_current_range,
    resolve_voltage_range,
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
    "mode": LoadMode.CC,
    "current_range": AUTO_RANGE,
    "voltage_range": AUTO_RANGE,
    "current_protection_enabled": False,
    "current_protection_a": 15.0,
    "current_protection_delay_s": 0.1,
    "power_protection_enabled": False,
    "power_protection_w": 300.0,
    "power_protection_delay_s": 0.1,
    # This is the documented turn-on voltage / latch setting, not a separate OVP command.
    "turn_on_voltage_v": None,
    "turn_on_voltage_latch_enabled": False,
    "sample_interval_s": 0.5,
    "steps": [
        {"name": "cc_2a", "current_a": 2.0, "duration_s": 5.0},
        {"name": "cc_5a", "current_a": 5.0, "duration_s": 5.0},
        {"name": "cc_10a", "current_a": 10.0, "duration_s": 5.0},
    ],
}


def main() -> int:
    csv_path = create_log_path("current_sequence")
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
        load.set_mode(RUN["mode"])
        load.set_current_range(
            "current",
            resolve_current_range(
                RUN["current_range"],
                *(step["current_a"] for step in RUN["steps"]),
            ),
        )
        load.set_voltage_range(
            "current",
            resolve_voltage_range(
                load,
                RUN["voltage_range"],
                RUN["turn_on_voltage_v"],
            ),
        )
        load.set_input_enabled(True)

        started = time.monotonic()
        sample_index = 0
        discharge_capacity_enabled = True
        try:
            for step in RUN["steps"]:
                load.set_current(float(step["current_a"]))
                step_started = time.monotonic()
                while time.monotonic() - step_started < float(step["duration_s"]):
                    row = measurement_row(
                        elapsed_s=time.monotonic() - started,
                        sample_index=sample_index,
                        step_name=str(step["name"]),
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
                    sleep_until_next_sample(float(RUN["sample_interval_s"]))
        finally:
            load.set_input_enabled(False)
            handle.close()

    print(f"Wrote sequence log to {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
