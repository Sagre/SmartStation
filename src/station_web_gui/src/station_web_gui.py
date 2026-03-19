#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64
import tornado.ioloop
import tornado.web
import tornado.websocket
import tornado.template
import json
import os
import threading
import traceback
from typing import Optional, Dict

class Config:
    """Centralized configuration settings."""
    def __init__(self):
        self.port = 8888
        self.template_path = os.path.join(os.path.dirname(__file__), "templates")
        self.static_path = os.path.join(os.path.dirname(__file__), "static")
        self.default_temperature = 25.0
        self.default_humidity = 60.0
        self.topic_config = {  # Example: configure topic names
            "temperature": "temperature",
            "humidity": "humidity",
            # Add more sensors here
        }

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
        for sensor_name, topic_name in self.app.config.topic_config.items():
            self.create_sensor_subscription(sensor_name, topic_name)

    def create_sensor_subscription(self, sensor_name: str, topic_name: str):
        """Creates a subscription for a specific sensor topic."""
        def callback(msg: Float64, sensor_name=sensor_name):
            try:
                Logger.debug(f"Received {sensor_name}: {msg.data}")
                self.send_sensor_data(sensor_name, msg.data)
            except Exception as e:
                Logger.error(f"Error in {sensor_name} callback: {e}")
                traceback.print_exc()

        subscription = self.create_subscription(
            Float64,
            topic_name,
            callback,
            10
        )
        self.topic_subscriptions[sensor_name] = subscription  # Keep track of subscriptions

    def send_sensor_data(self, sensor_name: str, value: float):
      """Sends sensor data to the WebSocket."""
      message = {"sensor_name": sensor_name, "value": value}
      try:
          if self.app.sensor_ws_handler:
              # Instead of updating data here, just send the message to the WS
              self.app.ioloop.add_callback(self.app.sensor_ws_handler.write_message, json.dumps(message))
      except Exception as e:
          Logger.error(f"Error sending data to sensor WebSocket: {e}")

class StationWebGUIApp:
    """Main application class managing the web GUI."""
    def __init__(self, config: Config):
        self.config = config
        self.temperature_value = config.default_temperature
        self.humidity_value = config.default_humidity
        self.sensor_ws_handler: Optional[SensorDataWebSocket] = None # single handler
        self.ros2_bridge: Optional[ROS2Bridge] = None
        self.ioloop = tornado.ioloop.IOLoop.current()

    def register_websocket_handler(self, handler: BaseWebSocketHandler):
        if isinstance(handler, SensorDataWebSocket):
            self.sensor_ws_handler = handler

    def unregister_websocket_handler(self, handler: BaseWebSocketHandler):
        if isinstance(handler, SensorDataWebSocket) and self.sensor_ws_handler == handler:
            self.sensor_ws_handler = None

    def make_app(self):
        app = tornado.web.Application([
            (r'/', HomeHandler, dict(template_loader=tornado.template.Loader(self.config.template_path))),
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
    def initialize(self, template_loader):
        self.template_loader = template_loader

    async def get(self):
        try:
            self.render("index.html")
        except Exception as e:
            print(f"Error in HomeHandler: {e}", flush=True)
            traceback.print_exc()
            self.set_status(500)
            self.write(f"Error loading template: {e}")

def main(args=None):
    rclpy.init(args=args)
    config = Config()
    app = StationWebGUIApp(config)
    app.run()

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    main()