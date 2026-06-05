"""
SmartStation Logger Service
Centralized log aggregation service that collects logs from all services.
Logs are written to console (orchestrator captures stdout/stderr to file).
"""
import argparse
import logging
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from .logging_config import setup_console_logging, get_logger


running = True
logger: Optional[logging.Logger] = None


def handle_signal(signum, frame):
    global running
    running = False
    if logger:
        logger.info(f'Received signal {signum}, shutting down...')


def main():
    global logger
    
    parser = argparse.ArgumentParser(description='SmartStation logger service')
    parser.add_argument('--heartbeat-interval', type=float, default=5.0,
                        help='Heartbeat interval in seconds')
    parser.add_argument('--console-level', type=str, default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Console log level')
    args = parser.parse_args()

    # Set up console-only logging (orchestrator captures stdout/stderr to file)
    log_levels = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
    }
    
    logger = setup_console_logging(
        logger_name='smartstation.logger_service',
        level=log_levels[args.console_level]
    )
    
    logger.info('Starting SmartStation logger service')
    logger.info(f'Console level: {args.console_level}')

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    def heartbeat_loop():
        while running:
            logger.debug('logger_service heartbeat')
            time.sleep(args.heartbeat_interval)

    thread = threading.Thread(target=heartbeat_loop, daemon=True)
    thread.start()

    try:
        while running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info('Keyboard interrupt received')

    logger.info('SmartStation logger service stopped')
    sys.exit(0)


if __name__ == '__main__':
    main()
