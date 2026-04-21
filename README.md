# siglent_driver

`siglent_driver` is a Python library for controlling a Siglent `SDL1030X` electronic load over SCPI.

It is set up for practical bench use:
- `pyvisa`, `pyvisa-py`, and `pyusb` are regular dependencies
- examples are editable scripts with a config block at the top
- CSV-writing examples prompt for a battery serial number and append it to the timestamped log filename
- both VISA resource strings and Linux `/dev/usbtmc*` paths are supported

## Install

```bash
pip install -e .
```

## Quick Start

```python
from siglent_driver import CurrentRange, LoadMode, SiglentSDL1030, VoltageRange

usb_resource = "USB0::0xF4EC::0x1621::YOUR_SERIAL_HERE::INSTR"

with SiglentSDL1030(usb_resource, visa_backend="@py") as load:
    load.set_4wire_enabled(True)
    load.set_mode(LoadMode.CC)
    load.set_current_range("current", CurrentRange.A5)
    load.set_voltage_range("current", VoltageRange.V36)
    load.set_current(5.0)
    load.set_input_enabled(True)
    print(load.measure_all())
    load.set_input_enabled(False)
```

Example VISA resource strings:

```python
usb_resource = "USB0::0xF4EC::0x1621::YOUR_SERIAL_HERE::INSTR"
lan_resource = "TCPIP0::192.168.1.55::inst0::INSTR"
```

## Examples

Each example has two blocks at the top:
- `CONNECTION` defaults to auto-detecting the SDL over VISA-over-USB with `pyvisa-py`, with explicit USB/LAN/USBTMC alternatives
- `RUN` for 4-wire sense, explicit or auto-selected fixed ranges, static-mode protections where applicable, documented turn-on voltage behavior, built-in battery stop conditions, current levels, timing, and sampling

Available examples:

- [cc_load_5a.py](/home/jasper/Documents/Wingtra/github/siglent_driver/examples/cc_load_5a.py): `5 A` run using the SDL's built-in stop conditions
- [dcir_battery_test.py](/home/jasper/Documents/Wingtra/github/siglent_driver/examples/dcir_battery_test.py): battery/DCIR console result
- [current_sequence_dict.py](/home/jasper/Documents/Wingtra/github/siglent_driver/examples/current_sequence_dict.py): CC sequence using a simple dict of steps (`2 A`, `5 A`, `10 A`)

Folder guide:
- [README.md](/home/jasper/Documents/Wingtra/github/siglent_driver/examples/README.md)

Run them from the repo root:

```bash
uv run python examples/cc_load_5a.py
uv run python examples/dcir_battery_test.py
uv run python examples/current_sequence_dict.py
```

The CC and sequence examples prompt for a battery serial number and write timestamped CSV files into `log/`, for example `20260421_120000_cc_load_5a_SN123.csv`. The DCIR example prints the final result to the console.

## Logging

The library stays quiet by default.

- Use `configure_logging(...)` for simple scripts.
- SCPI traffic is logged at `DEBUG`.
- Transport open/close events are logged at `INFO`.
- Current and voltage range helpers snap to the SDL1030's fixed hardware ranges.

## Supported Features

- CC, CV, CP, CR, and LED static modes
- current and voltage range helpers
- enum helpers for load modes and the fixed `5/30 A` and `36/150 V` ranges
- 4-wire sense control
- current slew helpers
- transient configuration
- current and power protection helpers
- LIST mode helpers
- trigger helpers
- battery-test helpers for CC/CP/CR plus DCR configuration helpers
- VISA and Linux USBTMC transports

## Caveat: DCIR

The driver now selects DCR explicitly with `:SOUR:BATT:MODE DCR` and then programs the dedicated `:SOUR:BATT:DCR:*` parameters. Even with that sequence, live testing on an `SDL1030X` running firmware `1.1.1.23R4` still showed a limitation:

- the battery test starts and finishes
- `:SOUR:BATT:DCR:RESult?` remains `0.0`
- `:SOUR:BATT:DISCHArg:TIMer?` and `:SOUR:BATT:DISCHArg:CAPability?` time out on that firmware

So the DCIR API is present, but remote execution appears firmware-dependent.

## Development

Run tests:

```bash
.venv/bin/pytest -q
```

Exercise a connected SDL1030 with conservative settings:

```bash
.venv/bin/python scripts/exercise_sdl1030.py --resource /dev/usbtmc0
```
