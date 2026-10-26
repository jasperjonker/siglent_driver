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
   The CC and sequence examples prompt for a battery serial number and write timestamped CSV files into `log/`, with the serial appended to the filename.
   The DCIR example prints the final result to the console.

Available scripts:

- `cc_load.py`: single-pack CC run with the SDL's built-in stop conditions
- `discharge_01c.py`: one pack at 0.1C with a required voltage cutoff
- `dcir_battery_test.py`: battery/DCIR console result
- `current_sequence_dict.py`: `2 A -> 5 A -> 10 A` sequence from a list of dicts

For `discharge_01c.py`, pass the pack serial, rated capacity in Ah, and
**pack-level cutoff voltage** in V. It calculates current as `capacity / 10`.
One process controls one SDL and one pack. With two SDLs on the same laptop,
start two processes and give each a different `--resource` VISA string or
`/dev/usbtmc*` path. Automatic USB selection works only when one SDL is found.
The script refuses to start if the selected load input is already on. The SDL
battery mode enforces the voltage stop internally. The sample CSV contains
voltage, current, power, integrated Ah, and integrated Wh; the summary CSV adds
instrument-reported capacity/time when available and the stop status. Integrated
totals are estimates from periodic samples. A reported instrument stop may also
be due to another protection condition; check the SDL front panel before
interpreting it as a voltage cutoff. Check pack and load current, voltage, and
power limits. Add `--four-wire` only when Kelvin sense leads are connected.

Run from the repo root with the synced environment:

```bash
uv run python examples/cc_load.py
# Example values only: use each pack's actual rating and specified cutoff.
uv run python examples/discharge_01c.py --serial PACK1 --capacity-ah 20 --cutoff-v 15 --resource /dev/usbtmc0
# On a second SDL, in another terminal:
uv run python examples/discharge_01c.py --serial PACK2 --capacity-ah 20 --cutoff-v 15 --resource /dev/usbtmc1
uv run python examples/dcir_battery_test.py
uv run python examples/current_sequence_dict.py
```
