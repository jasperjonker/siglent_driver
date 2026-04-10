from __future__ import annotations

import logging


DEFAULT_LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"


def configure_logging(
    level: int = logging.INFO,
    logger_name: str = "siglent_driver",
) -> logging.Logger:
    """Attach a simple stream handler for quick standalone scripts.

    Libraries should stay quiet by default, so this helper is optional.
    Applications with their own logging policy can ignore it and configure
    logging in the normal Python way.
    """

    logger = logging.getLogger(logger_name)
    handler = next(
        (entry for entry in logger.handlers if getattr(entry, "_siglent_driver_handler", False)),
        None,
    )
    if handler is None:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(DEFAULT_LOG_FORMAT))
        setattr(handler, "_siglent_driver_handler", True)
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger
