import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import rclpy
from rclpy.node import Node
import yaml

from .logging_config import get_log_file, get_logger, setup_child_process_logging, stop_child_process_logging

MANAGED_PROCESS_WAIT_SECONDS = 5.0
MONITOR_INTERVAL_SECONDS = 1.5

DEFAULT_CONFIG = {
    'mqtt_broker_ip': '127.0.0.1',
    'mqtt_broker_port': 1883,
    'web_port': 8888,
    'devices': {},
    'use_local_broker': True,
    'startup_retries': 3,
    'retry_backoff_seconds': 2,
    'web_host': '127.0.0.1',
}

SERVICE_ORDER = ['config', 'broker', 'bridge', 'web_gui']

SERVICE_COMMANDS = {
    'broker': ['mosquitto', '-c', '/etc/mosquitto/mosquitto.conf'],
    'bridge': ['ros2', 'run', 'mqtt_ros2_bridge', 'mqtt_ros2_bridge'],
    'web_gui': ['ros2', 'run', 'station_web_gui', 'station_web_gui'],
}

class OrchestratorNode(Node):
    def __init__(self, config_path: str):
        # Set up centralized logging first (before ROS2 node init)
        self.log_file = get_log_file()
        os.environ['SMARTSTATION_LOG_FILE'] = self.log_file
        self.logger = get_logger('smartstation.orchestrator')
        
        super().__init__('station_orchestrator')
        self.logger.info('Starting station_orchestrator')

        self.config_path = config_path
        self.config = self.load_and_validate_config(config_path)

        self.processes: Dict[str, subprocess.Popen] = {}
        self.process_log_threads: Dict[str, tuple] = {}
        self._shutdown_lock = threading.Lock()
        self._monitor_stop = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None

        self.shutdown_requested = False
        self.shutdown_reason: Optional[str] = None

        self.stop_existing_managed_processes()
        self.start_services()
        self._start_monitor_thread()
        self.logger.info('station_orchestrator initialization complete')

    def load_and_validate_config(self, config_path: str) -> Dict[str, Any]:
        if not os.path.exists(config_path):
            raise RuntimeError(f'Station config file not found: {config_path}')

        try:
            with open(config_path, 'r') as f:
                raw = yaml.safe_load(f)
        except Exception as e:
            raise RuntimeError(f'Failed to parse station config: {e}')

        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise RuntimeError('Station config must be a YAML mapping')

        config = DEFAULT_CONFIG.copy()
        config.update(raw)
        errors = self.validate_config(config)
        if errors:
            raise RuntimeError('Configuration validation failed: ' + '; '.join(errors))
        return config

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        if not isinstance(config.get('mqtt_broker_ip'), str) or not config['mqtt_broker_ip']:
            errors.append('mqtt_broker_ip must be a non-empty string')

        if not isinstance(config.get('mqtt_broker_port'), int):
            errors.append('mqtt_broker_port must be an integer')
        else:
            if not (1 <= config['mqtt_broker_port'] <= 65535):
                errors.append('mqtt_broker_port must be 1..65535')

        if not isinstance(config.get('web_port'), int):
            errors.append('web_port must be an integer')
        else:
            if not (1 <= config['web_port'] <= 65535):
                errors.append('web_port must be 1..65535')

        devices = config.get('devices')
        if not isinstance(devices, dict):
            errors.append('devices must be a mapping of device_id to display name')
        else:
            for device_id, display_name in devices.items():
                if not isinstance(device_id, str) or not device_id:
                    errors.append('device ids must be non-empty strings')
                if not isinstance(display_name, str) or not display_name:
                    errors.append(f'display name for device {device_id!r} must be a non-empty string')

        if not isinstance(config.get('use_local_broker'), bool):
            errors.append('use_local_broker must be true or false')
        if not isinstance(config.get('startup_retries'), int) or config['startup_retries'] < 0:
            errors.append('startup_retries must be zero or a positive integer')
        if not isinstance(config.get('retry_backoff_seconds'), (int, float)) or config['retry_backoff_seconds'] < 0:
            errors.append('retry_backoff_seconds must be zero or a positive number')
        if not isinstance(config.get('web_host'), str) or not config['web_host']:
            errors.append('web_host must be a non-empty string')

        return errors

    def stop_existing_managed_processes(self) -> None:
        self.logger.info('Checking for existing managed processes')
        try:
            ps_output = subprocess.check_output(['ps', '-eo', 'pid='], text=True)
        except Exception as e:
            self.logger.warning(f'Cannot inspect system processes: {e}')
            return

        pids_to_stop: List[int] = []
        for line in ps_output.splitlines():
            pid_text = line.strip()
            if not pid_text:
                continue
            try:
                pid = int(pid_text)
            except ValueError:
                continue
            if pid == os.getpid():
                continue
            cmdline = self.get_process_cmdline(pid)
            if not cmdline:
                continue
            if self.is_managed_command(cmdline):
                pids_to_stop.append(pid)

        if not pids_to_stop:
            return

        for pid in pids_to_stop:
            cmdline = self.get_process_cmdline(pid)
            self.logger.info(f'Stopping previous managed process {pid}: {cmdline}')
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
            except PermissionError as e:
                self.logger.warning(f'Unable to stop process {pid}: {e}')

        for pid in pids_to_stop:
            self.wait_for_process_exit(pid, timeout=MANAGED_PROCESS_WAIT_SECONDS)

        for pid in pids_to_stop:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                continue
            except PermissionError as e:
                self.logger.warning(f'Unable to inspect process {pid}: {e}')
                continue
            self.logger.warning(f'Managed process {pid} still running; sending SIGKILL')
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                continue
            except PermissionError as e:
                self.logger.warning(f'Unable to kill process {pid}: {e}')
            else:
                self.wait_for_process_exit(pid, timeout=2.0)

    def is_managed_command(self, args: str) -> bool:
        lower_args = args.lower()
        if 'station_orchestrator' in lower_args:
            if lower_args.count('station_orchestrator') >= 2 or 'orchestrator_node' in lower_args:
                return True
        for service_name, command in SERVICE_COMMANDS.items():
            if service_name == 'broker' and not self.config['use_local_broker']:
                continue
            if service_name == 'web_gui':
                if 'station_web_gui' in lower_args:
                    return True
                continue
            if service_name == 'bridge':
                if 'mqtt_ros2_bridge' in lower_args:
                    return True
                continue
            if service_name == 'broker' and 'mosquitto' in lower_args:
                return True
        return False

    def get_process_cmdline(self, pid: int) -> str:
        try:
            with open(f'/proc/{pid}/cmdline', 'rb') as f:
                raw = f.read()
            return raw.replace(b'\x00', b' ').decode('utf-8', errors='ignore').strip()
        except Exception:
            return ''

    def wait_for_process_exit(self, pid: int, timeout: float) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            except PermissionError:
                return
            time.sleep(0.1)

    def find_listening_pids(self, port: int) -> List[int]:
        pids = set()
        try:
            ss_output = subprocess.check_output(['ss', '-ltnp'], text=True, stderr=subprocess.DEVNULL)
        except Exception:
            return []

        for line in ss_output.splitlines():
            if f':{port} ' not in line and f':{port}\n' not in line and not line.strip().endswith(f':{port}'):
                continue
            if 'pid=' not in line:
                continue
            parts = line.split('pid=')
            for part in parts[1:]:
                pid_part = part.split(',')[0]
                try:
                    pid_match = int(pid_part)
                except ValueError:
                    continue
                pids.add(pid_match)
        return sorted(pids)

    def cleanup_service_port(self, service_name: str, port: int) -> None:
        if not self.check_tcp_port(self.config['web_host'] if service_name == 'web_gui' else self.config['mqtt_broker_ip'], port):
            return
        pids = self.find_listening_pids(port)
        if not pids:
            return
        for pid in pids:
            cmdline = self.get_process_cmdline(pid).lower()
            if service_name == 'web_gui' and 'station_web_gui' in cmdline:
                self.logger.info(f'Terminating stale web_gui process {pid} using port {port}')
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    continue
                except PermissionError as e:
                    self.logger.warning(f'Unable to stop process {pid}: {e}')
                else:
                    self.wait_for_process_exit(pid, timeout=5.0)
            elif service_name == 'broker' and 'mosquitto' in cmdline:
                self.logger.info(f'Terminating stale mosquitto process {pid} using port {port}')
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    continue
                except PermissionError as e:
                    self.logger.warning(f'Unable to stop process {pid}: {e}')
                else:
                    self.wait_for_process_exit(pid, timeout=5.0)
        time.sleep(1.0)
        if self.check_tcp_port(self.config['web_host'] if service_name == 'web_gui' else self.config['mqtt_broker_ip'], port):
            pids = self.find_listening_pids(port)
            for pid in pids:
                cmdline = self.get_process_cmdline(pid).lower()
                if service_name == 'web_gui' and 'station_web_gui' in cmdline:
                    self.logger.warning(f'Stale web_gui process {pid} still holds port {port}; killing it')
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        continue
                    except PermissionError as e:
                        self.logger.warning(f'Unable to kill process {pid}: {e}')
                    else:
                        self.wait_for_process_exit(pid, timeout=2.0)
                elif service_name == 'broker' and 'mosquitto' in cmdline:
                    self.logger.warning(f'Stale mosquitto process {pid} still holds port {port}; killing it')
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        continue
                    except PermissionError as e:
                        self.logger.warning(f'Unable to kill process {pid}: {e}')
                    else:
                        self.wait_for_process_exit(pid, timeout=2.0)
            if self.check_tcp_port(self.config['web_host'] if service_name == 'web_gui' else self.config['mqtt_broker_ip'], port):
                service_port_name = 'web_gui' if service_name == 'web_gui' else 'mosquitto'
                raise RuntimeError(f'Port {port} is still in use and cannot be reclaimed for {service_port_name}')

    def cleanup_service_prestart(self, service_name: str) -> None:
        if service_name == 'web_gui':
            self.cleanup_service_port(service_name, self.config['web_port'])
        elif service_name == 'broker' and self.config['use_local_broker']:
            self.cleanup_service_port(service_name, self.config['mqtt_broker_port'])

    def start_services(self) -> None:
        self.logger.info('Starting managed services in defined order')
        for service_name in SERVICE_ORDER:
            if service_name == 'config':
                self.logger.info('Configuration validated successfully')
                continue
            if service_name == 'broker' and not self.config['use_local_broker']:
                self.logger.info('Skipping local MQTT broker because use_local_broker is false')
                continue
            self.start_service_with_retries(service_name)

    def start_service_with_retries(self, service_name: str) -> None:
        retries = self.config['startup_retries']
        backoff = float(self.config['retry_backoff_seconds'])
        last_error = None
        for attempt in range(1, retries + 2):
            try:
                self.logger.info(f'Starting service {service_name} (attempt {attempt}/{retries + 1})')
                self.cleanup_service_prestart(service_name)
                proc = self.start_service(service_name)
                if proc and self.check_service_health(service_name, proc, wait_seconds=5):
                    self.processes[service_name] = proc
                    self._start_service_monitor_thread(service_name, proc)
                    self.logger.info(f'Service {service_name} started successfully')
                    return
                last_error = f'health check failed for {service_name}'
                self.stop_process_by_name(service_name)
            except RuntimeError as e:
                last_error = str(e)
            if attempt <= retries:
                self.logger.info(f'Retrying {service_name} after {backoff} seconds: {last_error}')
                time.sleep(backoff)
                backoff *= 1.5

        raise RuntimeError(f'Failed to start {service_name} after {retries + 1} attempts: {last_error}')

    def start_service(self, service_name: str) -> subprocess.Popen:
        command = SERVICE_COMMANDS[service_name]
        env = os.environ.copy()
        env['SMARTSTATION_ORCHESTRATOR'] = '1'
        env['SMARTSTATION_LOG_FILE'] = self.log_file
        cwd = os.getcwd()
        capture_output = service_name == 'broker'

        proc = subprocess.Popen(
            command,
            env=env,
            cwd=cwd,
            start_new_session=True,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
        )

        if capture_output:
            log_threads = setup_child_process_logging(proc, service_name)
            self.process_log_threads[service_name] = log_threads

        return proc

    def _start_service_monitor_thread(self, service_name: str, process: subprocess.Popen) -> None:
        def monitor_service() -> None:
            returncode = process.wait()
            if self.shutdown_requested:
                return
            self.logger.error(
                f'Service {service_name} exited unexpectedly with code {returncode}'
            )
            self.shutdown_all('Unexpected service exit')

        thread = threading.Thread(
            target=monitor_service,
            name=f'smartstation-monitor-{service_name}',
            daemon=True,
        )
        thread.start()

    def check_service_health(self, service_name: str, process: subprocess.Popen, wait_seconds: float) -> bool:
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            if process.poll() is not None:
                self.logger.warning(f'Service {service_name} exited early with {process.returncode}')
                return False
            if service_name == 'broker':
                if self.check_tcp_port(self.config['mqtt_broker_ip'], self.config['mqtt_broker_port']):
                    return True
            elif service_name == 'web_gui':
                if self.check_tcp_port(self.config['web_host'], self.config['web_port']):
                    return True
            else:
                return True
            time.sleep(0.5)
        return service_name not in ('broker', 'web_gui') or self.check_tcp_port(self.config['web_host'] if service_name == 'web_gui' else self.config['mqtt_broker_ip'], self.config['web_port'] if service_name == 'web_gui' else self.config['mqtt_broker_port'])

    def check_tcp_port(self, host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            return False

    def _start_monitor_thread(self) -> None:
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name='smartstation-monitor',
            daemon=True,
        )
        self._monitor_thread.start()

    def _monitor_loop(self) -> None:
        while not self._monitor_stop.wait(MONITOR_INTERVAL_SECONDS):
            if self.shutdown_requested:
                return
            for name, process in list(self.processes.items()):
                if process.poll() is not None:
                    self.logger.error(
                        f'Service {name} exited unexpectedly with code {process.returncode}'
                    )
                    self.shutdown_all('Unexpected service exit')
                    return

    def shutdown_all(self, reason: Optional[str] = None) -> None:
        with self._shutdown_lock:
            if self.shutdown_requested:
                return
            self.shutdown_requested = True
            self.shutdown_reason = reason
        self._monitor_stop.set()
        if reason:
            self.logger.info(f'Initiating shutdown: {reason}')
        for name, process in list(self.processes.items()):
            if process.poll() is None:
                self.logger.info(f'Terminating {name}')
                try:
                    process.terminate()
                except Exception as e:
                    self.logger.warning(f'Failed to terminate {name}: {e}')
        deadline = time.time() + 5.0
        while time.time() < deadline and any(p.poll() is None for p in self.processes.values()):
            time.sleep(0.2)
        for name, process in list(self.processes.items()):
            if process.poll() is None:
                self.logger.warning(f'Killing {name}')
                try:
                    process.kill()
                except Exception as e:
                    self.logger.warning(f'Failed to kill {name}: {e}')
        # Stop all log capture threads
        for name, log_threads in self.process_log_threads.items():
            stop_child_process_logging(log_threads)
        self.process_log_threads.clear()
        self.processes.clear()
        try:
            self.destroy_node()
        except Exception:
            pass
        try:
            rclpy.shutdown()
        except Exception:
            pass

    def stop_process_by_name(self, service_name: str) -> None:
        process = self.processes.get(service_name)
        if process and process.poll() is None:
            self.logger.info(f'Stopping service process {service_name}')
            try:
                process.terminate()
            except Exception as e:
                self.logger.warning(f'Failed to terminate {service_name}: {e}')
            try:
                process.wait(timeout=3)
            except Exception:
                process.kill()
        # Stop log capture threads
        log_threads = self.process_log_threads.pop(service_name, None)
        if log_threads:
            stop_child_process_logging(log_threads)
        self.processes.pop(service_name, None)


def find_default_config_path() -> str:
    env_path = os.environ.get('SMARTSTATION_CONFIG_PATH')
    if env_path:
        return env_path
    workspace_root = Path(os.getcwd())
    candidate = workspace_root / 'config' / 'station_params.yaml'
    if candidate.exists():
        return str(candidate)
    raise RuntimeError('Station config file not found and SMARTSTATION_CONFIG_PATH is unset')


def main(argv=None):
    parser = argparse.ArgumentParser(description='SmartStation orchestrator')
    parser.add_argument('--config', dest='config_path', default=find_default_config_path(), help='Path to station_params.yaml')
    args, unknown_args = parser.parse_known_args(argv)

    rclpy.init(args=unknown_args)
    node = None
    exit_code = 0
    try:
        node = OrchestratorNode(config_path=args.config_path)
        rclpy.spin(node)
        if node.shutdown_reason == 'Unexpected service exit':
            exit_code = 1
    except KeyboardInterrupt:
        if node:
            node.logger.info('KeyboardInterrupt received')
    except Exception as exc:
        logger = node.logger if node else get_logger('smartstation.orchestrator')
        logger.error(f'FATAL: {exc}')
        if node:
            node.shutdown_all(str(exc))
        sys.exit(1)
    finally:
        if node and not node.shutdown_requested:
            node.shutdown_all('shutdown requested')
        if node and node._monitor_thread and node._monitor_thread.is_alive():
            node._monitor_thread.join(timeout=2.0)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
