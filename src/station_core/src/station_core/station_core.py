#!/usr/bin/env python3
import os
import shutil
import subprocess
import threading

import yaml
import rclpy
from rclpy.node import Node


class StationCore(Node):
    def __init__(self):
        super().__init__('station_core')
        self.get_logger().info('Station Core node started')

        self.config_file = os.path.join(os.getcwd(), 'config', 'station_params.yaml')
        self.station_config = self.load_station_config()

        self.mqtt_broker_ip = self.station_config.get('mqtt_broker_ip', '192.168.2.197')
        self.mqtt_broker_port = self.station_config.get('mqtt_broker_port', 1883)
        self.web_port = self.station_config.get('web_port', 8888)
        self.sensor_config = self.station_config.get('sensor_config', [])

        self.child_processes = []
        self.shutdown_event = threading.Event()

        self.start_services()
        self.monitor_thread = threading.Thread(target=self.monitor_children, daemon=True)
        self.monitor_thread.start()

    def start_services(self):
        self.start_mosquitto()
        self.start_ros2_service('station_mqtt_bridge', 'station_mqtt_bridge')
        self.start_ros2_service('station_web_gui', 'station_web_gui')

    def start_mosquitto(self):
        mosquitto_bin = shutil.which('mosquitto')
        if not mosquitto_bin:
            self.get_logger().error('mosquitto binary not found in PATH; cannot start MQTT broker')
            return

        self.start_process(
            'mosquitto',
            [mosquitto_bin, '-c', '/etc/mosquitto/mosquitto.conf'],
        )

    def start_ros2_service(self, package_name: str, executable_name: str):
        ros2_bin = shutil.which('ros2')
        if not ros2_bin:
            self.get_logger().error('ros2 CLI not found in PATH; cannot start ROS2 service')
            return

        command = [ros2_bin, 'run', package_name, executable_name]

        if package_name == 'station_mqtt_bridge':
            command.extend([
                '--ros-args',
                '-p', f'mqtt_broker_ip:={self.mqtt_broker_ip}',
                '-p', f'mqtt_broker_port:={self.mqtt_broker_port}',
            ])
        elif package_name == 'station_web_gui':
            command.extend([
                '--ros-args',
                '-p', f'web_port:={self.web_port}',
            ])

        self.start_process(
            executable_name,
            command,
        )

    def load_station_config(self):
        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f)
        except FileNotFoundError:
            self.get_logger().error(f'Station config file not found: {self.config_file}')
            return {}
        except Exception as e:
            self.get_logger().error(f'Failed to load station config: {e}')
            return {}

        if not isinstance(config, dict):
            self.get_logger().error('Station config file must contain a YAML mapping')
            return {}

        return config.get('station_config', {})

    def start_process(self, name: str, command: list[str]):
        try:
            self.get_logger().info(f'Starting {name}: {" ".join(command)}')
            process = subprocess.Popen(command, env=os.environ.copy())
            self.child_processes.append((name, process))
            self.get_logger().info(f'{name} started with PID {process.pid}')
        except Exception as exc:
            self.get_logger().error(f'Failed to start {name}: {exc}')

    def monitor_children(self):
        while not self.shutdown_event.wait(1.0):
            for name, process in list(self.child_processes):
                returncode = process.poll()
                if returncode is not None:
                    if returncode != 0:
                        self.get_logger().error(
                            f'Service "{name}" exited unexpectedly with code {returncode}'
                        )
                    else:
                        self.get_logger().warning(
                            f'Service "{name}" exited with code {returncode}'
                        )

                    self.child_processes.remove((name, process))
                    self.shutdown_other_services(f'Child service "{name}" stopped with code {returncode}')
                    return

    def shutdown_other_services(self, message: str):
        if self.shutdown_event.is_set():
            return

        self.get_logger().error(message)
        self.shutdown_event.set()

        for name, process in list(self.child_processes):
            if process.poll() is None:
                self.get_logger().info(f'Terminating {name} (PID {process.pid})')
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.get_logger().warning(f'{name} did not exit gracefully; killing it')
                    process.kill()
        self.child_processes.clear()

    def destroy_node(self):
        self.get_logger().info('Shutting down Station Core and child services...')
        self.shutdown_event.set()

        for name, process in list(self.child_processes):
            if process.poll() is None:
                self.get_logger().info(f'Terminating {name} (PID {process.pid})')
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.get_logger().warning(f'{name} did not exit gracefully; killing it')
                    process.kill()
        self.child_processes.clear()

        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    station_core = StationCore()
    try:
        rclpy.spin(station_core)
    except KeyboardInterrupt:
        pass
    finally:
        station_core.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
