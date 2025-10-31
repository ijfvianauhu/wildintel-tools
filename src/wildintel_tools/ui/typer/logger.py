import logging
from pathlib import Path
# Create module logger
logger = logging.getLogger(__name__)

def setup_logging(app:str, verbosity: int, logger_file:Path=None) -> None:
    """Configure logging for all modules.

    Args:
        verbosity: Logging level (0=WARNING, 1=INFO, 2=DEBUG)
        :param app:
    """
    # Map verbosity to logging level
    log_levels = {
        0: logging.WARNING,
        1: logging.INFO,
        2: logging.DEBUG,
    }
    log_level = log_levels.get(verbosity, logging.INFO)

    # Configure root logger
    
    logging_conf = {
       "level": log_level,
        #"format":"%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        "format":"[%(levelname)s] %(name)s: %(message)s",
        "datefmt":"%Y-%m-%d %H:%M:%S",
    }

    if logger_file:
        logging_conf["filename"]=str(logger_file)
        logging_conf["filemode"]="a"
    
    logging.basicConfig(**logging_conf)
    
    # Set level for this module's logger
    logger.setLevel(log_level)

    # Set level for trapper_tools modules
    logging.getLogger(app).setLevel(log_level)

    # Quiet some noisy modules
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

