"""
Centralized logging configuration.
This module provides a reusable function to set up and get a logger instance.
"""

import logging
import sys

def setup_logger(name: str) -> logging.Logger:
    """
    Configures and returns a logger instance.

    Args:
        name: The name of the logger, typically the module name
              (__name__). This helps in identifying the source of
              log messages.

    Returns:
        A configured logging.Logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Prevent adding duplicate handlers if the logger is already configured
    if not logger.handlers:
        # Create a StreamHandler to output logs to the console
        handler = logging.StreamHandler(sys.stdout)
        
        # Define the log message format
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
