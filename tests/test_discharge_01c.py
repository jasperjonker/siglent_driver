import argparse
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


def test_refuses_to_change_an_active_load(monkeypatch: pytest.MonkeyPatch) -> None:
    load = MagicMock()
    load.is_input_enabled.return_value = True
    monkeypatch.setattr(module, "connect_from_config", lambda config: nullcontext(load))

    with pytest.raises(RuntimeError, match="already ON"):
        module.run(args())

    load.set_input_enabled.assert_not_called()


def test_configures_cutoff_before_enabling_and_turns_off_after_stop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    load = MagicMock()
    load.is_input_enabled.side_effect = [False, False, True, False]
    load.measure_voltage.return_value = 12.0
    load.is_battery_voltage_stop_enabled.return_value = True
    load.get_battery_voltage_stop.return_value = 10.0
    load.measure_all.return_value = SimpleNamespace(voltage_v=11.0, current_a=2.0, power_w=22.0)
    load.get_battery_discharge_capacity.return_value = 0.1
    load.get_battery_discharge_time.return_value = 180.0
    monkeypatch.setattr(module, "connect_from_config", lambda config: nullcontext(load))
    monkeypatch.setattr(module, "create_log_path", lambda stem, battery_serial: tmp_path / "run.csv")
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

    sample_path, summary_path = module.run(args())

    assert load.mock_calls.index(call.configure_battery_stops(voltage_v=10.0, capacity_ah=None, timer_s=None)) < load.mock_calls.index(call.set_input_enabled(True))
    assert load.mock_calls.index(call.get_battery_voltage_stop()) < load.mock_calls.index(call.set_input_enabled(True))
    assert load.mock_calls.index(call.set_input_enabled(False)) > load.mock_calls.index(call.set_input_enabled(True))
    assert sample_path.read_text().count("\n") == 2
    assert "instrument stopped" in summary_path.read_text()
