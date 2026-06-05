"""
Centralized logging configuration for SmartStation.

All services use get_logger(module_name) for consistent output to the
terminal and ~/.smartstation/logs/smartstation.log with the format:
  timestamp | severity | module | message
"""
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Optional

LOG_FORMAT = '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

_configured_loggers: set[str] = set()
_config_lock = threading.Lock()


def get_log_file() -> str:
    log_dir = Path.home() / '.smartstation' / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    return str(log_dir / 'smartstation.log')


def get_logger(module_name: str, log_file: Optional[str] = None) -> logging.Logger:
    """Return a logger that writes to stdout and the shared log file."""
    resolved_log_file = log_file or os.environ.get('SMARTSTATION_LOG_FILE') or get_log_file()

    with _config_lock:
        logger = logging.getLogger(module_name)
        if module_name in _configured_loggers:
            return logger

        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        log_path = Path(resolved_log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(resolved_log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        _configured_loggers.add(module_name)
        return logger


def service_logger_name(service_name: str) -> str:
    return f'smartstation.{service_name}'


def setup_child_process_logging(
    process: 'subprocess.Popen',
    service_name: str,
) -> tuple:
    """
    Capture stdout/stderr from external processes (e.g. mosquitto) and
    forward lines through the standard SmartStation logger for that service.
    """
    import queue
    import subprocess

    logger = get_logger(service_logger_name(service_name))

    stdout_queue = queue.Queue()
    stderr_queue = queue.Queue()
    stop_event = threading.Event()

    def read_stream(stream, queue_obj):
        try:
            for line in iter(stream.readline, b''):
                if stop_event.is_set():
                    break
                try:
                    decoded = line.decode('utf-8', errors='replace').rstrip('\n')
                except Exception:
                    decoded = str(line)
                if decoded:
                    queue_obj.put(decoded)
        except Exception:
            pass
        finally:
            queue_obj.put(None)

    def process_queue(queue_obj, level):
        while not stop_event.is_set():
            try:
                message = queue_obj.get(timeout=0.1)
            except queue.Empty:
                continue
            if message is None:
                break
            logger.log(level, message)

    stdout_thread = threading.Thread(
        target=read_stream,
        args=(process.stdout, stdout_queue),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=read_stream,
        args=(process.stderr, stderr_queue),
        daemon=True,
    )
    stdout_processor = threading.Thread(
        target=process_queue,
        args=(stdout_queue, logging.INFO),
        daemon=True,
    )
    stderr_processor = threading.Thread(
        target=process_queue,
        args=(stderr_queue, logging.WARNING),
        daemon=True,
    )

    stdout_thread.start()
    stderr_thread.start()
    stdout_processor.start()
    stderr_processor.start()

    return (stdout_thread, stderr_thread, stdout_processor, stderr_processor, stop_event)


def stop_child_process_logging(threads: tuple) -> None:
    """Stop the logging capture threads."""
    _, _, _, _, stop_event = threads
    stop_event.set()
    for thread in threads[:-1]:
        thread.join(timeout=1.0)
