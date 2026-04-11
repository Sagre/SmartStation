#!/usr/bin/env python3
import os
import json
import threading
import traceback
from typing import Optional, Dict, List, Any

import tornado.ioloop
import tornado.template
import tornado.web
import tornado.websocket
import yaml

import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from std_msgs.msg import Float64, String

class Config:
    """Centralized configuration settings."""
    def __init__(self, node: Node):
        share_dir = get_package_share_directory('station_web_gui')
        self.station_config_path = node.declare_parameter(
            'station_config_path',
            os.path.join(os.getcwd(), 'config', 'station_params.yaml')
        ).value

        self.station_config = self.load_station_config()

        self.port = self.station_config.get('web_port', 8888)
        self.template_path = node.declare_parameter('template_path', os.path.join(share_dir, 'templates')).value
        self.static_path = node.declare_parameter('static_path', os.path.join(share_dir, 'static')).value
        self.sensor_config = self.station_config.get('sensor_config', [])

        if not self.sensor_config:
            self.sensor_config = self.load_sensor_config()

    def load_station_config(self) -> Dict[str, Any]:
        try:
            with open(self.station_config_path, 'r') as f:
                config = yaml.safe_load(f)
        except FileNotFoundError:
            Logger.error(f'Station config file not found: {self.station_config_path}')
            return {}
        except Exception as e:
            Logger.error(f'Error loading station config: {e}')
            return {}

        if not isinstance(config, dict):
            Logger.error('Station config file must contain a YAML mapping')
            return {}

        return config.get('station_config', {})

    def load_sensor_config(self) -> List[Dict]:
        """Loads sensor configuration from the station config file."""
        if not self.station_config:
            return []

        sensor_config = self.station_config.get('sensor_config', [])
        if not isinstance(sensor_config, list):
            Logger.error('sensor_config in station config must be a list')
            return []

        return sensor_config

class Logger:
    """Standardized logging utility."""
    @staticmethod
    def info(message: str):
        print(f"INFO: {message}")

    @staticmethod
    def error(message: str):
        print(f"ERROR: {message}")

    @staticmethod
    def debug(message: str):
        print(f"DEBUG: {message}")

class BaseWebSocketHandler(tornado.websocket.WebSocketHandler):
    """Base class for WebSocket handlers with shared functionality."""
    def __init__(self, *args, **kwargs):
        Logger.info(f"{self.__class__.__name__} Kwargs: {kwargs}")
        web_gui_application = kwargs.pop('web_gui_application', None)
        super().__init__(*args, **kwargs)
        self.web_gui_application = web_gui_application
        self.last_update = 0

    def open(self):
        Logger.info(f"{self.__class__.__name__} WebSocket opened")
        self.web_gui_application.register_websocket_handler(self)

    def on_close(self):
        Logger.info(f"{self.__class__.__name__} WebSocket closed")
        self.web_gui_application.unregister_websocket_handler(self)

class SensorDataWebSocket(BaseWebSocketHandler):
    """Generic WebSocket handler for sensor data."""
    def open(self):
        super().open()
        self.sensor_data: Dict[str, float] = {}  # Store the latest sensor data, {sensor_name: value}

    def on_message(self, message):
        try:
            print(f"Received message: {message}")
            data = json.loads(message)
            if "sensor_name" in data and "value" in data:
                self.sensor_data[data["sensor_name"]] = data["value"]
                # No need to send_update, the client will handle the logic,
                #  as the old implementation.
        except json.JSONDecodeError:
            Logger.error("Invalid JSON received")
        except Exception as e:
            Logger.error(f"Error processing message: {e}")


class ROS2Bridge(Node):
    """ROS2 node for handling sensor data."""
    def __init__(self, app):
        super().__init__('ros2_web_bridge')
        self.app = app
        self.topic_subscriptions = {}
        self.initialize_subscriptions()
        Logger.info('ROS2 Bridge Node started')

    def initialize_subscriptions(self):
        """Creates subscriptions based on the config."""
        for sensor in self.app.config.sensor_config:
            self.create_sensor_subscription(sensor)

    def create_sensor_subscription(self, sensor_config: Dict):
        """Creates a subscription for a specific sensor topic."""
        sensor_id = sensor_config["id"]
        topic_name = sensor_config["topic"]

        def callback(msg: String, sensor_id=sensor_id):
            try:
                Logger.debug(f"Received {sensor_id}: {msg.data}")
                json_data = json.loads(msg.data)
                self.send_sensor_data(sensor_id, json_data["value"])
            except json.JSONDecodeError:
                Logger.error(f"Invalid JSON received on topic '{topic_name}': {msg.data}")
            except Exception as e:
                Logger.error(f"Error in {sensor_id} callback: {e}")
                traceback.print_exc()

        subscription = self.create_subscription(
            String,
            topic_name,
            callback,
            10
        )
        self.topic_subscriptions[sensor_id] = subscription  # Keep track of subscriptions

    def send_sensor_data(self, sensor_name: str, value: float):
      """Sends sensor data to the WebSocket."""
      message = {"sensor_name": sensor_name, "value": value}
      try:
          if self.app.sensor_ws_handler:
              # Instead of updating data here, just send the message to the WS
              self.app.ioloop.add_callback(self.app.sensor_ws_handler.write_message, json.dumps(message))
          # Also update the last sensor value in StationWebGUIApp
          self.app.update_last_sensor_value(sensor_name, value)
      except Exception as e:
          Logger.error(f"Error sending data to sensor WebSocket: {e}")

class StationWebGUIApp:
    """Main application class managing the web GUI."""
    def __init__(self, config: Config):
        self.config = config
        self.sensor_ws_handler: Optional[SensorDataWebSocket] = None # single handler
        self.ros2_bridge: Optional[ROS2Bridge] = None
        self.ioloop = tornado.ioloop.IOLoop.current()
        self.last_sensor_values: Dict[str, float] = {} # Store last known sensor values

    def register_websocket_handler(self, handler: BaseWebSocketHandler):
        if isinstance(handler, SensorDataWebSocket):
            self.sensor_ws_handler = handler

    def unregister_websocket_handler(self, handler: BaseWebSocketHandler):
        if isinstance(handler, SensorDataWebSocket) and self.sensor_ws_handler == handler:
            self.sensor_ws_handler = None

    def update_last_sensor_value(self, sensor_name: str, value: float):
        """Updates the last known value for a sensor."""
        self.last_sensor_values[sensor_name] = value

    def make_app(self):
        from tornado import escape
        app = tornado.web.Application([
            (r'/', HomeHandler, dict(template_loader=tornado.template.Loader(self.config.template_path),
                                       web_gui_app=self)), # Pass the web_gui_app instance
            (r'/ws', SensorDataWebSocket, dict(web_gui_application=self)), # Changed to a single websocket
            (r'/static/(.*)', tornado.web.StaticFileHandler, {'path': self.config.static_path}),
        ], template_path=self.config.template_path, debug=True)
        app.sensor_ws_handler = None
        return app

    def start_ros2_bridge(self):
        self.ros2_bridge = ROS2Bridge(self)
        rclpy.spin(self.ros2_bridge)
        self.ros2_bridge.destroy_node()
        rclpy.shutdown()

    def run(self):
        app = self.make_app()
        app.listen(self.config.port)
        Logger.info(f"Tornado server started on port {self.config.port}")

        ros2_thread = threading.Thread(target=self.start_ros2_bridge, daemon=True)
        ros2_thread.start()

        try:
            self.ioloop.start()
        except Exception as e:
            Logger.error(f"Tornado IOLoop encountered an error: {e}")
            traceback.print_exc()

class HomeHandler(tornado.web.RequestHandler):
    def initialize(self, template_loader, web_gui_app): # Receive web_gui_app
        self.template_loader = template_loader
        self.web_gui_app = web_gui_app # Store the web_gui_app instance

    async def get(self):
        try:
            import json
            adapted = []
            for sensor, value in self.web_gui_app.last_sensor_values.items():
                dic = {}
                dic["sensor_name"] = sensor
                dic["value"] = value
                adapted.append(dic)
                
            print(f"Last sensor values: {adapted}")
            last_sensor_values_json = json.dumps(adapted)
            # Pass the sensor configuration and the last sensor values to the template
            self.render("index.html", sensor_config=self.web_gui_app.config.sensor_config,
                        last_sensor_values=last_sensor_values_json) # Access via web_gui_app
        except Exception as e:
            print(f"Error in HomeHandler: {e}", flush=True)
            traceback.print_exc()
            self.set_status(500)
            self.write(f"Error loading template: {e}")

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