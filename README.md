# Siglent Python Driver

`siglent_driver` is a standalone Python package for the Siglent SDL1030 electronic load.

## Features

- SCPI control over VISA
- Works with USBTMC and VISA-addressable LAN resources
- Static mode control for CC/CV/CP/CR/LED
- Input enable control
- Voltage, current, power, and resistance setpoints
- Voltage, current, power, and resistance measurements
- Basic LIST-mode configuration helpers
- Trigger-source and trigger helpers

## Install

```bash
pip install -e .
```

With VISA support:

```bash
pip install -e .[visa]
```

## Usage

```python
from siglent_driver import SiglentSDL1030

load = SiglentSDL1030("USB0::0xF4EC::0xEE38::SDL1XCAD2R0001::INSTR")
load.open()
load.set_mode("current")
load.set_current(5.0)
load.set_input_enabled(True)
print(load.measure_all())
load.close()
```

## Build

```bash
hatch build
```

or:

```bash
uv run --with hatch hatch build
```

## Versioning

Versions come from git tags via `hatch-vcs`.

Suggested tag format:

```bash
git tag v0.1.0
```

If no git metadata is available, the build falls back to `0.1.0.dev0`.

## Release Readiness

Before publishing to PyPI:

- add a `LICENSE`
- add real project URLs in `pyproject.toml`
- validate the driver on the actual SDL1030
- build from a tagged git checkout
