#!/usr/bin/env python3
from __future__ import annotations

import argparse
from contextlib import suppress
import time

from siglent_driver import SiglentSDL1030


def measurement_snapshot(load: SiglentSDL1030) -> dict[str, float]:
    return {
        "voltage_v": round(load.measure_voltage(), 6),
        "current_a": round(load.measure_current(), 6),
        "power_w": round(load.measure_power(), 6),
        "resistance_ohm": round(load.measure_resistance(), 6),
    }


def print_result(name: str, result: dict[str, object]) -> None:
    status = "ok" if result.get("ok", False) else "failed"
    print(f"[{status}] {name}")
    for key, value in result.items():
        if key == "ok":
            continue
        print(f"  {key}: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Exercise a connected Siglent SDL1030 with conservative settings.")
    parser.add_argument("--resource", default="/dev/usbtmc0", help="VISA resource string or Linux USBTMC device path.")
    parser.add_argument("--cc-current-a", type=float, default=0.10)
    parser.add_argument("--cp-power-w", type=float, default=1.0)
    parser.add_argument("--cr-ohms", type=float, default=1000.0)
    parser.add_argument("--cv-delta-v", type=float, default=0.01)
    parser.add_argument("--cv-ocp-a", type=float, default=0.25)
    parser.add_argument("--dynamic-a-level-a", type=float, default=0.05)
    parser.add_argument("--dynamic-b-level-a", type=float, default=0.10)
    parser.add_argument("--dynamic-a-width-s", type=float, default=0.20)
    parser.add_argument("--dynamic-b-width-s", type=float, default=0.20)
    parser.add_argument("--dynamic-slew-a-per-us", type=float, default=0.10)
    parser.add_argument("--dcr-current1-a", type=float, default=0.10)
    parser.add_argument("--dcr-current2-a", type=float, default=0.20)
    parser.add_argument("--dcr-time1-s", type=float, default=1.0)
    parser.add_argument("--dcr-time2-s", type=float, default=1.0)
    args = parser.parse_args()

    load = SiglentSDL1030(args.resource)
    results: dict[str, dict[str, object]] = {}

    def run_step(name: str, fn) -> None:
        try:
            results[name] = {"ok": True, **fn()}
        except Exception as exc:  # pragma: no cover - hardware exercise
            results[name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            with suppress(Exception):
                load.set_input_enabled(False)

    load.open()
    initial_sense = False
    initial_current_protection: tuple[bool, float, float] | None = None
    initial_power_protection: tuple[bool, float, float] | None = None
    open_circuit_voltage = 0.0

    try:
        print(f"Connected: {load.identify()}")
        load.set_input_enabled(False)
        open_circuit_voltage = load.measure_voltage()
        print(f"Open-circuit voltage: {open_circuit_voltage:.6f} V")

        initial_sense = load.is_4wire_enabled()
        initial_current_protection = (
            load.is_current_protection_enabled(),
            load.get_current_protection_level(),
            load.get_current_protection_delay(),
        )
        initial_power_protection = (
            load.is_power_protection_enabled(),
            load.get_power_protection_level(),
            load.get_power_protection_delay(),
        )

        static_voltage_range = 36.0 if open_circuit_voltage <= 36.0 else 150.0

        run_step(
            "sense_toggle",
            lambda: {
                "initial": initial_sense,
                "off_state": _toggle_sense(load, False),
                "on_state": _toggle_sense(load, True),
            },
        )

        def _range_step() -> dict[str, object]:
            targets = ("current", "voltage", "power", "resistance", "battery", "list")
            ranges: dict[str, object] = {}
            for target in targets:
                load.set_current_range(target, 1.0)
                low_i = load.get_current_range(target)
                load.set_current_range(target, 10.0)
                high_i = load.get_current_range(target)
                load.set_voltage_range(target, 12.0)
                low_v = load.get_voltage_range(target)
                load.set_voltage_range(target, 48.0)
                high_v = load.get_voltage_range(target)
                ranges[target] = {
                    "current_low": low_i,
                    "current_high": high_i,
                    "voltage_low": low_v,
                    "voltage_high": high_v,
                }
            load.set_resistance_range("resistance", "low")
            resistance_low = load.get_resistance_range("resistance")
            load.set_resistance_range("resistance", "upper")
            resistance_high = load.get_resistance_range("resistance")
            return {
                "ranges": ranges,
                "resistance_low": resistance_low,
                "resistance_high": resistance_high,
            }

        run_step("range_configuration", _range_step)

        def _cc_step() -> dict[str, object]:
            load.set_mode("current")
            load.set_current_range("current", args.cc_current_a)
            load.set_voltage_range("current", static_voltage_range)
            load.set_current(args.cc_current_a)
            return _apply_input_and_measure(load, settle_s=0.35)

        run_step("cc_mode", _cc_step)

        def _cr_step() -> dict[str, object]:
            load.set_mode("resistance")
            load.set_current_range("resistance", args.cc_current_a)
            load.set_voltage_range("resistance", static_voltage_range)
            load.set_resistance_range("resistance", "upper")
            load.set_resistance(args.cr_ohms)
            return _apply_input_and_measure(load, settle_s=0.35)

        run_step("cr_mode", _cr_step)

        def _cp_step() -> dict[str, object]:
            load.set_mode("power")
            load.set_current_range("power", args.cc_current_a)
            load.set_voltage_range("power", static_voltage_range)
            load.set_power(args.cp_power_w)
            return _apply_input_and_measure(load, settle_s=0.35)

        run_step("cp_mode", _cp_step)

        def _cv_step() -> dict[str, object]:
            cv_target = max(0.0, open_circuit_voltage - args.cv_delta_v)
            load.set_current_protection_enabled(True)
            load.set_current_protection_level(args.cv_ocp_a)
            load.set_current_protection_delay(0.1)
            load.set_mode("voltage")
            load.set_current_range("voltage", args.cv_ocp_a)
            load.set_voltage_range("voltage", static_voltage_range)
            load.set_voltage(cv_target)
            data = _apply_input_and_measure(load, settle_s=0.20)
            data["target_voltage_v"] = round(cv_target, 6)
            data["input_still_enabled"] = load.is_input_enabled()
            load.set_input_enabled(False)
            return data

        run_step("cv_mode", _cv_step)

        def _protection_step() -> dict[str, object]:
            load.set_current_protection_enabled(True)
            load.set_current_protection_level(args.cv_ocp_a)
            load.set_current_protection_delay(0.1)
            load.set_power_protection_enabled(True)
            load.set_power_protection_level(max(args.cp_power_w + 1.0, 2.0))
            load.set_power_protection_delay(0.1)
            return {
                "current_protection_enabled": load.is_current_protection_enabled(),
                "current_protection_level_a": load.get_current_protection_level(),
                "current_protection_delay_s": load.get_current_protection_delay(),
                "power_protection_enabled": load.is_power_protection_enabled(),
                "power_protection_level_w": load.get_power_protection_level(),
                "power_protection_delay_s": load.get_power_protection_delay(),
            }

        run_step("protection_configuration", _protection_step)

        def _dynamic_step() -> dict[str, object]:
            load.set_current_range("current_transient", args.dynamic_b_level_a)
            load.set_voltage_range("current_transient", static_voltage_range)
            load.configure_transient(
                mode="current",
                waveform="toggle",
                a_level=args.dynamic_a_level_a,
                b_level=args.dynamic_b_level_a,
                a_width_s=args.dynamic_a_width_s,
                b_width_s=args.dynamic_b_width_s,
            )
            load.set_current_transient_slew_positive(args.dynamic_slew_a_per_us)
            load.set_current_transient_slew_negative(args.dynamic_slew_a_per_us)
            data = _apply_input_and_measure(
                load,
                settle_s=args.dynamic_a_width_s + args.dynamic_b_width_s + 0.20,
            )
            data["transient_mode"] = load.get_transient_function()
            data["waveform"] = load.get_transient_waveform_mode("current")
            return data

        run_step("dynamic_current", _dynamic_step)

        def _battery_dcr_step() -> dict[str, object]:
            load.enter_battery_mode()
            load.set_battery_mode("current")
            load.set_current_range("battery", args.dcr_current2_a)
            load.set_voltage_range("battery", static_voltage_range)
            load.set_battery_level(args.dcr_current1_a)
            load.set_battery_voltage_cutoff_enabled(False)
            load.set_battery_capability_cutoff_enabled(False)
            load.set_battery_timer_cutoff(args.dcr_time1_s + args.dcr_time2_s + 1.0)
            load.set_battery_timer_cutoff_enabled(True)
            load.configure_battery_dcr(
                current1_a=args.dcr_current1_a,
                current2_a=args.dcr_current2_a,
                time1_s=args.dcr_time1_s,
                time2_s=args.dcr_time2_s,
            )
            load.set_input_enabled(True)
            time.sleep(max(args.dcr_time1_s * 0.75, 0.2))
            current_phase_1 = load.measure_current()
            time.sleep(max(args.dcr_time2_s + 0.75, 0.5))
            current_phase_2 = load.measure_current()
            result = load.get_battery_dcr_result()
            data = {
                "battery_mode": load.get_battery_mode(),
                "current_phase_1_a": round(current_phase_1, 6),
                "current_phase_2_a": round(current_phase_2, 6),
                "dcr_ohm": round(result, 6),
            }
            load.set_input_enabled(False)
            if result <= 0.0:
                raise RuntimeError(
                    "Battery test completed, but `:SOUR:BATT:DCR:RESult?` stayed at 0.0 "
                    "and the expected DCIR current-step behavior did not materialize."
                )
            return data

        run_step("battery_dcir", _battery_dcr_step)

    finally:
        with suppress(Exception):
            load.set_input_enabled(False)
        if initial_current_protection is not None:
            with suppress(Exception):
                load.set_current_protection_enabled(initial_current_protection[0])
                load.set_current_protection_level(initial_current_protection[1])
                load.set_current_protection_delay(initial_current_protection[2])
        if initial_power_protection is not None:
            with suppress(Exception):
                load.set_power_protection_enabled(initial_power_protection[0])
                load.set_power_protection_level(initial_power_protection[1])
                load.set_power_protection_delay(initial_power_protection[2])
        with suppress(Exception):
            load.set_4wire_enabled(initial_sense)
        with suppress(Exception):
            load.close()

    failed = 0
    for name, result in results.items():
        print_result(name, result)
        if not result.get("ok", False):
            failed += 1

    if failed:
        print(f"Completed with {failed} failed step(s). The load input was left OFF for safety.")
        return 1
    print("All scripted SDL1030 steps completed. The load input was left OFF for safety.")
    return 0


def _toggle_sense(load: SiglentSDL1030, enabled: bool) -> bool:
    load.set_4wire_enabled(enabled)
    return load.is_4wire_enabled()


def _apply_input_and_measure(load: SiglentSDL1030, settle_s: float) -> dict[str, object]:
    load.set_input_enabled(True)
    time.sleep(settle_s)
    snapshot = measurement_snapshot(load)
    load.set_input_enabled(False)
    return snapshot


if __name__ == "__main__":
    raise SystemExit(main())
