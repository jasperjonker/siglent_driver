import logging

from .core import InstrumentError, Measurement
from .logging_utils import configure_logging
from .siglent import (
    CURRENT_RANGE_VALUES,
    VOLTAGE_RANGE_VALUES,
    BatteryMode,
    CurrentRange,
    LoadMode,
    ResistanceRange,
    SiglentSDL1030,
    TransientMode,
    TransientWaveform,
    TriggerSource,
    VoltageRange,
    WaveformMetric,
)

try:
    from ._version import version as __version__
except ImportError:  # pragma: no cover
    from importlib.metadata import version as _pkg_version

    try:
        __version__ = _pkg_version("siglent_driver")
    except Exception:  # pragma: no cover
        __version__ = "0.0.0+unknown"

__all__ = [
    "CURRENT_RANGE_VALUES",
    "BatteryMode",
    "CurrentRange",
    "InstrumentError",
    "LoadMode",
    "Measurement",
    "ResistanceRange",
    "SiglentSDL1030",
    "TransientMode",
    "TransientWaveform",
    "TriggerSource",
    "VOLTAGE_RANGE_VALUES",
    "VoltageRange",
    "WaveformMetric",
    "__version__",
    "configure_logging",
]

logging.getLogger(__name__).addHandler(logging.NullHandler())
