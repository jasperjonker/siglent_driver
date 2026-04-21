# Examples

Each example in this folder follows the same layout:

1. `CONNECTION`
   Use this section to choose how you reach the load.
   The default is:
   - auto-detected VISA over USB: `AUTO_USB_VISA_RESOURCE`
   Other options are:
   - explicit VISA over USB: `USB_VISA_RESOURCE`
   - VISA over LAN: `LAN_VISA_RESOURCE`
   - Linux USBTMC: `USBTMC_RESOURCE`

2. `RUN`
   Use this section to change the actual test behavior:
   - `enable_4wire` for Kelvin sense
   - explicit range values or `AUTO` for the fixed SDL `5/30 A` and `36/150 V` ranges
   - `current_protection_*` and `power_protection_*` for the static CC sequence example
   - documented `turn_on_voltage_*` settings when relevant
   - built-in battery stop conditions `voltage_stop_v`, `capacity_stop_ah`, and `timer_stop_s` for the battery examples
   - currents, timing, and sample interval
   - sequence steps for the dict-driven example

3. Output
   The CC and sequence examples write timestamped CSV files into `log/`.
   The DCIR example prints the final result to the console.

Available scripts:

- [`cc_load_5a.py`](/home/jasper/Documents/Wingtra/github/siglent_driver/examples/cc_load_5a.py): 5 A run with the SDL's built-in stop conditions
- [`dcir_battery_test.py`](/home/jasper/Documents/Wingtra/github/siglent_driver/examples/dcir_battery_test.py): battery/DCIR console result
- [`current_sequence_dict.py`](/home/jasper/Documents/Wingtra/github/siglent_driver/examples/current_sequence_dict.py): `2 A -> 5 A -> 10 A` sequence from a list of dicts

Run from the repo root with the synced environment:

```bash
uv run python examples/cc_load_5a.py
uv run python examples/dcir_battery_test.py
uv run python examples/current_sequence_dict.py
```
