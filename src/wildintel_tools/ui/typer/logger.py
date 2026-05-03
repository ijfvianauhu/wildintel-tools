"""
Logging configuration utilities for the Trapper Tools application.

This module provides a simple and consistent logging setup used across
all Trapper Tools components. It allows configuring the logging verbosity
level (e.g., WARNING, INFO, DEBUG) and optionally logging to a file.

Typical usage example:
    .. code-block:: python

        from wildintel_tools.utils.logging_config import setup_logging

        setup_logging(app="trapper_tools", verbosity=2, logger_file="trapper.log")

        import logging
        logger = logging.getLogger(__name__)
        logger.info("Logging system initialized.")

"""
import logging
from pathlib import Path
# Create module logger
logger = logging.getLogger(__name__)

def setup_logging(app:str, verbosity: int, logger_file:Path=None) -> None:
    """
    Configure logging for all modules in the application.

    This function sets up a unified logging configuration with an adjustable
    verbosity level. Logs can be directed either to the console or to a file
    if a path is provided.

    :param app: The base name of the application package (e.g., ``"wildintel_tools"``).
    :type app: str
    :param verbosity: Logging verbosity level.
                      ``0`` → WARNING, ``1`` → INFO, ``2`` → DEBUG.
    :type verbosity: int
    :param logger_file: Optional path to a log file. If provided, logs are written there.
    :type logger_file: pathlib.Path, optional
    :return: None
    :rtype: None

    Example:
        .. code-block:: python

            setup_logging("trapper_tools", verbosity=1)
            logger = logging.getLogger(__name__)
            logger.info("This is an info message.")
    """

    log_levels = {
        0: logging.WARNING,
        1: logging.INFO,
        2: logging.DEBUG,
    }
    log_level = log_levels.get(verbosity, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # basicConfig is a no-op when handlers already exist (e.g. added by third-party
    # libraries during import), so we replace them explicitly.
    root_logger.handlers.clear()

    fmt = logging.Formatter("[%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler: logging.Handler = (
        logging.FileHandler(str(logger_file), mode="a") if logger_file else logging.StreamHandler()
    )
    handler.setFormatter(fmt)
    root_logger.addHandler(handler)

    logger.setLevel(log_level)
    logging.getLogger(app).setLevel(log_level)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

