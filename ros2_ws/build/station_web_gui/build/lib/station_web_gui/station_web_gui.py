#!/usr/bin/env python3
import os
import json
import logging
import sys
import threading
import traceback
from typing import Optional, Dict, List, Any
import sqlite3
from datetime import datetime

import tornado.ioloop
import tornado.template
import tornado.web
import tornado.websocket
import yaml

import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from std_msgs.msg import String

from .sensor_metadata import SensorMetadataRegistry

try:
    from station_orchestrator.logging_config import get_logger
except ImportError:
    def get_logger(name: str):
        logger = logging.getLogger(name)
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S',
            ))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

logger = get_logger('smartstation.web_gui')


class Config:
    def __init__(self, node: Node):
        share_dir = get_package_share_directory('station_web_gui')
        self.station_config_path = node.declare_parameter(
            'station_config_path',
            os.path.join(os.getcwd(), 'config', 'station_params.yaml')
        ).value
        self.db_path = node.declare_parameter('db_path', os.path.expanduser('~/.smartstation/logs.db')).value

        self.station_config = self.load_station_config()
        self.port = self.station_config.get('web_port', 8888)
        self.template_path = node.declare_parameter('template_path', os.path.join(share_dir, 'templates')).value
        self.static_path = node.declare_parameter('static_path', os.path.join(share_dir, 'static')).value
        self.sensor_config = self.load_sensor_config()

    def load_station_config(self) -> Dict[str, Any]:
        try:
            with open(self.station_config_path, 'r') as f:
                config = yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f'Station config file not found: {self.station_config_path}')
            return {}
        except Exception as e:
            logger.error(f'Error loading station config: {e}')
            return {}
        return config if isinstance(config, dict) else {}

    def load_sensor_config(self) -> List[Dict]:
        if not self.station_config:
            logger.error('No station config loaded')
            return []
        
        devices = self.station_config.get('devices', {})
        if not devices or not isinstance(devices, dict):
            logger.error('No devices found in station config')
            return []
        
        sensor_configs = []
        for device_id, display_name in devices.items():
            configs = SensorMetadataRegistry.generate_sensor_config(device_id, display_name)
            sensor_configs.extend(configs)
        
        logger.info(f'Config: {sensor_configs}')
        return sensor_configs

class BaseWebSocketHandler(tornado.websocket.WebSocketHandler):
    def __init__(self, *args, **kwargs):
        logger.info(f"{self.__class__.__name__} Kwargs: {kwargs}")
        web_gui_application = kwargs.pop('web_gui_application', None)
        super().__init__(*args, **kwargs)
        self.web_gui_application = web_gui_application
        self.last_update = 0

    def open(self):
        logger.info(f"{self.__class__.__name__} WebSocket opened")
        self.web_gui_application.register_websocket_handler(self)

    def on_close(self):
        logger.info(f"{self.__class__.__name__} WebSocket closed")
        self.web_gui_application.unregister_websocket_handler(self)

class SensorDataWebSocket(BaseWebSocketHandler):
    def open(self):
        super().open()
        self.sensor_data: Dict[str, float] = {}

    def on_message(self, message):
        try:
            logger.debug(f'Received message: {message}')
            data = json.loads(message)
            if "sensor_name" in data and "value" in data:
                self.sensor_data[data["sensor_name"]] = data["value"]
        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
        except Exception as e:
            logger.error(f"Error processing message: {e}")


class ROS2Bridge(Node):
    def __init__(self, app):
        super().__init__('ros2_web_bridge')
        self.app = app
        self.topic_subscriptions = {}
        self.control_publishers = {}
        self.initialize_subscriptions()
        self.initialize_publishers()
        logger.info('ROS2 Bridge Node started')

    def initialize_subscriptions(self):
        for sensor in self.app.config.sensor_config:
            self.create_sensor_subscription(sensor)

    def initialize_publishers(self):
        """Create publishers for control topics for each device"""
        devices = self.app.config.station_config.get('devices', {})
        for device_id in devices.keys():
            control_topic = f'control/{device_id}'
            try:
                publisher = self.create_publisher(String, control_topic, 10)
                self.control_publishers[device_id] = publisher
                logger.info(f'Created control publisher for {control_topic}')
            except Exception as e:
                logger.error(f'Error creating control publisher for {control_topic}: {e}')

    def create_sensor_subscription(self, sensor_config: Dict):
        sensor_id = sensor_config["id"]
        topic_name = sensor_config["topic"]
        device_id = sensor_config["device_id"]

        def callback(msg: String, sensor_id=sensor_id, device_id=device_id, topic_name=topic_name):
            try:
                logger.debug(f"Received {sensor_id}: {msg.data}")
                json_data = json.loads(msg.data)
                self.send_sensor_data(sensor_id, device_id, json_data["value"], topic_name)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received on topic '{topic_name}': {msg.data}")
            except Exception as e:
                logger.error(f"Error in {sensor_id} callback: {e}")
                logger.debug(traceback.format_exc())

        subscription = self.create_subscription(
            String,
            topic_name,
            callback,
            10
        )
        self.topic_subscriptions[sensor_id] = subscription
        logger.info(f'Created subscription for topic {topic_name}')

    def send_sensor_data(self, sensor_id: str, device_id: str, value: float, topic: str):
        timestamp = datetime.now().isoformat()
        message = {
            "sensor_id": sensor_id,
            "device_id": device_id,
            "value": value,
            "timestamp": timestamp,
            "topic": topic
        }
        try:
            for handler in self.app.sensor_ws_handlers:
                self.app.ioloop.add_callback(handler.write_message, json.dumps(message))
            self.app.update_last_sensor_value(sensor_id, value, timestamp)
        except Exception as e:
            logger.error(f"Error sending data to sensor WebSocket: {e}")

    def publish_control_message(self, device_id: str, action: str):
        """Publish a control message to a device"""
        try:
            if device_id in self.control_publishers:
                msg = String()
                msg.data = action
                self.control_publishers[device_id].publish(msg)
                logger.info(f'Published control message to {device_id}: {action}')
            else:
                logger.error(f'No control publisher for device {device_id}')
        except Exception as e:
            logger.error(f'Error publishing control message: {e}')

class StationWebGUIApp:
    def __init__(self, config: Config):
        self.config = config
        self.sensor_ws_handlers: List[SensorDataWebSocket] = []
        self.ros2_bridge: Optional[ROS2Bridge] = None
        self.ioloop = tornado.ioloop.IOLoop.current()
        self.last_sensor_values: Dict[str, Dict[str, Any]] = {}

    def register_websocket_handler(self, handler: BaseWebSocketHandler):
        if isinstance(handler, SensorDataWebSocket):
            self.sensor_ws_handlers.append(handler)
            logger.info(f'Registered WebSocket handler. Total handlers: {len(self.sensor_ws_handlers)}')

    def unregister_websocket_handler(self, handler: BaseWebSocketHandler):
        if isinstance(handler, SensorDataWebSocket) and handler in self.sensor_ws_handlers:
            self.sensor_ws_handlers.remove(handler)
            logger.info(f'Unregistered WebSocket handler. Total handlers: {len(self.sensor_ws_handlers)}')

    def update_last_sensor_value(self, sensor_id: str, value: float, timestamp: str):
        self.last_sensor_values[sensor_id] = {"value": value, "timestamp": timestamp}

    def publish_control_action(self, device_id: str, action: str):
        """Publish a control action to a device via ROS2"""
        try:
            if self.ros2_bridge:
                self.ros2_bridge.publish_control_message(device_id, action)
        except Exception as e:
            logger.error(f"Error publishing control action: {e}")

    def make_app(self):
        app = tornado.web.Application([
            (r'/', HomeHandler, dict(template_loader=tornado.template.Loader(self.config.template_path),
                                       web_gui_app=self)),
            (r'/ws', SensorDataWebSocket, dict(web_gui_application=self)),
            (r'/control', ControlHandler, dict(web_gui_app=self, template_loader=tornado.template.Loader(self.config.template_path))),
            (r'/api/control', ControlAPIHandler, dict(web_gui_app=self)),
            (r'/static/(.*)', tornado.web.StaticFileHandler, {'path': self.config.static_path}),
            (r'/logs', LogsHandler, dict(web_gui_app=self)),
        ], template_path=self.config.template_path, debug=True)
        return app

    def start_ros2_bridge(self):
        self.ros2_bridge = ROS2Bridge(self)
        rclpy.spin(self.ros2_bridge)
        self.ros2_bridge.destroy_node()
        rclpy.shutdown()

    def run(self):
        app = self.make_app()
        app.listen(self.config.port)
        logger.info(f"Tornado server started on port {self.config.port}")

        ros2_thread = threading.Thread(target=self.start_ros2_bridge, daemon=True)
        ros2_thread.start()

        try:
            self.ioloop.start()
        except Exception as e:
            logger.error(f"Tornado IOLoop encountered an error: {e}")
            logger.debug(traceback.format_exc())

class HomeHandler(tornado.web.RequestHandler):
    def initialize(self, template_loader, web_gui_app):
        self.template_loader = template_loader
        self.web_gui_app = web_gui_app

    async def get(self):
        try:
            import json
            adapted = []
            for sensor_id, data in self.web_gui_app.last_sensor_values.items():
                adapted.append({
                    "sensor_id": sensor_id,
                    "value": data.get("value"),
                    "timestamp": data.get("timestamp")
                })

            last_sensor_values_json = json.dumps(adapted)
            self.render("index.html", sensor_config=self.web_gui_app.config.sensor_config,
                        last_sensor_values=last_sensor_values_json)
        except Exception as e:
            logger.error(f'Error in HomeHandler: {e}')
            logger.debug(traceback.format_exc())
            self.set_status(500)
            self.write(f"Error loading template: {e}")

class LogsHandler(tornado.web.RequestHandler):
    def initialize(self, web_gui_app):
        self.web_gui_app = web_gui_app

    async def get(self):
        try:
            db_path = self.web_gui_app.config.db_path
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, timestamp, device_id, log_level, message, topic
                    FROM logs
                    ORDER BY timestamp DESC
                    LIMIT 100
                    """
                )
                logs = [dict(row) for row in cursor.fetchall()]
            self.render("logs.html", logs=logs)
        except Exception as e:
            logger.error(f'Error in LogsHandler: {e}')
            logger.debug(traceback.format_exc())
            self.set_status(500)
            self.write(f"Error retrieving logs: {e}")

class ControlHandler(tornado.web.RequestHandler):
    def initialize(self, web_gui_app, template_loader):
        self.web_gui_app = web_gui_app
        self.template_loader = template_loader

    async def get(self):
        try:
            import json
            devices_config = self.web_gui_app.config.station_config.get('devices', {})
            devices = [
                {
                    "id": device_id,
                    "name": display_name,
                    "battery": self.web_gui_app.last_sensor_values.get(f"{device_id}_battery", {}).get("value", "N/A")
                }
                for device_id, display_name in devices_config.items()
            ]
            devices_json = json.dumps(devices)
            self.render("control.html", devices=devices_json, devices_list=devices)
        except Exception as e:
            logger.error(f'Error in ControlHandler: {e}')
            logger.debug(traceback.format_exc())
            self.set_status(500)
            self.write(f"Error loading control page: {e}")

class ControlAPIHandler(tornado.web.RequestHandler):
    def initialize(self, web_gui_app):
        self.web_gui_app = web_gui_app

    async def post(self):
        try:
            data = json.loads(self.request.body)
            device_id = data.get('device_id')
            action = data.get('action')
            
            if not device_id or not action:
                self.set_status(400)
                self.write({"error": "Missing device_id or action"})
                return
            
            self.web_gui_app.publish_control_action(device_id, action)
            self.write({"status": "success", "message": f"Control action sent to {device_id}"})
        except Exception as e:
            logger.error(f"Error in ControlAPIHandler: {e}")
            self.set_status(500)
            self.write({"error": str(e)})

def main(args=None):
    rclpy.init(args=args)
    config_node = rclpy.create_node('station_web_gui')
    config = Config(config_node)
    config_node.destroy_node()

    app = StationWebGUIApp(config)
    app.run()

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main()
