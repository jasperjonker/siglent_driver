#!/usr/bin/env python3
"""Run the battery/DCIR workflow and print the final result.

Edit `CONNECTION` to choose USBTMC, VISA-over-USB, or VISA-over-LAN.
Edit `RUN` to change 4-wire sense, I/V range, OCP/OPP, timing, current levels,
and stop conditions.

Note: on the tested SDL1030X firmware, the DCIR result may stay at `0.0`.
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
    "battery_mode": BatteryMode.DCR,
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
    "current1_a": 0.0,
    "current2_a": 4.0,
    "time1_s": 1.0,
    "time2_s": 5.0,
    "result_wait_margin_s": 1.0,
    # The programming guide documents BATT:LEV for CC/CP/CR battery tests, not DCR.
    # Keep this as None unless your unit needs the old workaround.
    "battery_level_a": None,
}


def main() -> int:
    with connect_from_config(CONNECTION) as load:
        apply_common_settings(load, RUN)
        load.enter_battery_mode()
        load.set_current_range("battery", RUN["current_range"])
        load.set_voltage_range("battery", RUN["voltage_range"])
        load.set_battery_mode(RUN["battery_mode"])
        battery_level_a = RUN.get("battery_level_a")
        if isinstance(battery_level_a, (int, float)):
            load.set_battery_level(float(battery_level_a))
        load.configure_battery_dcr(
            current1_a=float(RUN["current1_a"]),
            current2_a=float(RUN["current2_a"]),
            time1_s=float(RUN["time1_s"]),
            time2_s=float(RUN["time2_s"]),
        )

        wait_s = float(RUN["time1_s"]) + float(RUN["time2_s"]) + float(RUN["result_wait_margin_s"])
        load.set_input_enabled(True)
        final_dcir = 0.0
        try:
            time.sleep(wait_s)
            final_dcir = load.get_battery_dcr_result()
        finally:
            load.set_input_enabled(False)

    print(f"Final DCIR result: {final_dcir:.6f} ohm")
    if final_dcir <= 0.0:
        print("DCIR result stayed at 0.0 on this firmware.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
