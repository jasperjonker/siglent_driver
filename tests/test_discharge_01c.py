import argparse
import csv
from contextlib import nullcontext
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
sys.path.insert(0, str(EXAMPLES))
spec = spec_from_file_location("discharge_01c", EXAMPLES / "discharge_01c.py")
assert spec is not None and spec.loader is not None
module = module_from_spec(spec)
spec.loader.exec_module(module)


def args() -> argparse.Namespace:
    return argparse.Namespace(
        serial="A", capacity_ah=20.0, cutoff_v=10.0, resource="/dev/usbtmc0",
        four_wire=False, sample_interval_s=0.1, max_duration_s=10.0,
    )


def ready_load(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MagicMock:
    load = MagicMock()
    load.measure_voltage.return_value = 12.0
    load.is_battery_voltage_stop_enabled.return_value = True
    load.get_battery_voltage_stop.return_value = 10.0
    load.measure_all.return_value = SimpleNamespace(voltage_v=11.0, current_a=2.0, power_w=22.0)
    load.get_battery_discharge_capacity.return_value = 0.1
    load.get_battery_discharge_time.return_value = 180.0
    monkeypatch.setattr(module, "connect_from_config", lambda config: nullcontext(load))
    monkeypatch.setattr(module, "create_log_path", lambda stem, battery_serial: tmp_path / "run.csv")
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    return load


def test_refuses_to_change_an_active_load(monkeypatch: pytest.MonkeyPatch) -> None:
    load = MagicMock()
    load.is_input_enabled.return_value = True
    monkeypatch.setattr(module, "connect_from_config", lambda config: nullcontext(load))

    with pytest.raises(RuntimeError, match="already ON"):
        module.run(args())

    assert load.mock_calls == [call.is_input_enabled()]


def test_configures_cutoff_before_enabling_and_turns_off_after_stop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    load = ready_load(monkeypatch, tmp_path)
    load.is_input_enabled.side_effect = [False, False, True, False]
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(module.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: setattr(clock, "now", clock.now + seconds))

    sample_path, summary_path = module.run(args())

    assert load.mock_calls.index(call.configure_battery_stops(voltage_v=10.0, capacity_ah=None, timer_s=None)) < load.mock_calls.index(call.set_input_enabled(True))
    assert load.mock_calls.index(call.get_battery_voltage_stop()) < load.mock_calls.index(call.set_input_enabled(True))
    assert load.mock_calls.index(call.set_battery_level(2.0)) < load.mock_calls.index(call.set_input_enabled(True))
    assert load.mock_calls.index(call.set_input_enabled(False)) > load.mock_calls.index(call.set_input_enabled(True))
    assert sample_path.read_text().count("\n") == 2
    with summary_path.open(newline="") as handle:
        summary = next(csv.DictReader(handle))
    assert "instrument stopped" in summary["stop"]
    assert float(summary["capacity_Ah"]) > 0
    assert float(summary["energy_Wh"]) > 0


@pytest.mark.parametrize("enabled, readback", [(False, 10.0), (True, 9.0)])
def test_refuses_unverified_voltage_cutoff(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, enabled: bool, readback: float,
) -> None:
    load = ready_load(monkeypatch, tmp_path)
    load.is_input_enabled.return_value = False
    load.is_battery_voltage_stop_enabled.return_value = enabled
    load.get_battery_voltage_stop.return_value = readback

    with pytest.raises(RuntimeError, match="voltage cutoff readback"):
        module.run(args())

    load.set_input_enabled.assert_not_called()


def test_maximum_duration_caps_sleep(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    load = ready_load(monkeypatch, tmp_path)
    load.is_input_enabled.side_effect = [False, False, True]
    clock = SimpleNamespace(now=0.0)
    sleeps = []
    monkeypatch.setattr(module.time, "monotonic", lambda: clock.now)

    def advance(seconds: float) -> None:
        sleeps.append(seconds)
        clock.now += seconds

    monkeypatch.setattr(module.time, "sleep", advance)
    run_args = args()
    run_args.sample_interval_s = 3600.0
    run_args.max_duration_s = 1.0

    module.run(run_args)

    assert sleeps == [1.0]
    assert clock.now == 1.0
    load.set_input_enabled.assert_any_call(False)
    with (tmp_path / "run_summary.csv").open(newline="") as handle:
        summary = next(csv.DictReader(handle))
    assert float(summary["capacity_Ah"]) > 0


def test_interruption_writes_summary_and_turns_off(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    load = ready_load(monkeypatch, tmp_path)
    load.is_input_enabled.side_effect = [False, False, True]

    def interrupt_sleep(seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(module.time, "sleep", interrupt_sleep)

    with pytest.raises(KeyboardInterrupt):
        module.run(args())

    load.set_input_enabled.assert_any_call(False)
    with (tmp_path / "run_summary.csv").open(newline="") as handle:
        summary = next(csv.DictReader(handle))
    assert summary["stop"] == "aborted (KeyboardInterrupt)"
