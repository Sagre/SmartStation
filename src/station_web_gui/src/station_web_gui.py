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
from typing import Optional

class Config:
    """Centralized configuration settings."""
    def __init__(self):
        self.port = 8888
        self.template_path = os.path.join(os.path.dirname(__file__), "templates")
        self.static_path = os.path.join(os.path.dirname(__file__), "static")
        self.default_temperature = 25.0
        self.default_humidity = 60.0

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
        super().__init__(*args, **kwargs)
        self.application = kwargs.get('application')
        self.last_update = 0

    def open(self):
        Logger.info(f"{self.__class__.__name__} WebSocket opened")
        self.application.register_websocket_handler(self)

    def on_close(self):
        Logger.info(f"{self.__class__.__name__} WebSocket closed")
        self.application.unregister_websocket_handler(self)

class TemperatureWebSocket(BaseWebSocketHandler):
    """Handles temperature WebSocket connections."""
    def on_message(self, message):
        try:
            data = json.loads(message)
            if "temperature" in data:
                self.application.update_temperature(data["temperature"])
        except json.JSONDecodeError:
            Logger.error("Invalid JSON received")

    def send_update(self, temperature: float):
        self.write_message(json.dumps({"temperature": temperature}))

class HumidityWebSocket(BaseWebSocketHandler):
    """Handles humidity WebSocket connections."""
    def on_message(self, message):
        try:
            data = json.loads(message)
            if "humidity" in data:
                self.application.update_humidity(data["humidity"])
        except json.JSONDecodeError:
            Logger.error("Invalid JSON received")

    def send_update(self, humidity: float):
        self.write_message(json.dumps({"humidity": humidity}))

class ROS2Bridge(Node):
    """ROS2 node for handling sensor data."""
    def __init__(self, app):
        super().__init__('ros2_web_bridge')
        self.app = app
        self.temperature_value = app.config.default_temperature
        self.humidity_value = app.config.default_humidity

        self.temperature_subscription = self.create_subscription(
            Float64,
            'temperature',
            self.temperature_callback,
            10
        )
        self.humidity_subscription = self.create_subscription(
            Float64,
            'humidity',
            self.humidity_callback,
            10
        )
        Logger.info('ROS2 Bridge Node started')

    def temperature_callback(self, msg: Float64):
        try:
            self.temperature_value = msg.data
            Logger.debug(f"Received temperature: {self.temperature_value}")
            self.app.update_temperature(self.temperature_value)
        except Exception as e:
            Logger.error(f"Error in temperature_callback: {e}")
            traceback.print_exc()

    def humidity_callback(self, msg: Float64):
        try:
            self.humidity_value = msg.data
            Logger.debug(f"Received humidity: {self.humidity_value}")
            self.app.update_humidity(self.humidity_value)
        except Exception as e:
            Logger.error(f"Error in humidity_callback: {e}")
            traceback.print_exc()

class StationWebGUIApp:
    """Main application class managing the web GUI."""
    def __init__(self, config: Config):
        self.config = config
        self.temperature_value = config.default_temperature
        self.humidity_value = config.default_humidity
        self.temperature_ws_handler: Optional[TemperatureWebSocket] = None
        self.humidity_ws_handler: Optional[HumidityWebSocket] = None
        self.ros2_bridge: Optional[ROS2Bridge] = None
        self.ioloop = tornado.ioloop.IOLoop.current()

    def register_websocket_handler(self, handler: BaseWebSocketHandler):
        if isinstance(handler, TemperatureWebSocket):
            self.temperature_ws_handler = handler
        elif isinstance(handler, HumidityWebSocket):
            self.humidity_ws_handler = handler

    def unregister_websocket_handler(self, handler: BaseWebSocketHandler):
        if isinstance(handler, TemperatureWebSocket) and self.temperature_ws_handler == handler:
            self.temperature_ws_handler = None
        elif isinstance(handler, HumidityWebSocket) and self.humidity_ws_handler == handler:
            self.humidity_ws_handler = None

    def update_temperature(self, temperature: float):
        self.temperature_value = temperature
        if self.temperature_ws_handler:
            try:
                self.temperature_ws_handler.send_update(temperature)
            except Exception as e:
                Logger.error(f"Error sending temperature to WebSocket: {e}")

    def update_humidity(self, humidity: float):
        self.humidity_value = humidity
        if self.humidity_ws_handler:
            try:
                self.humidity_ws_handler.send_update(humidity)
            except Exception as e:
                Logger.error(f"Error sending humidity to WebSocket: {e}")

    def make_app(self):
        return tornado.web.Application([
            (r'/', HomeHandler, dict(template_loader=tornado.template.Loader(self.config.template_path), app=self)),
            (r'/temperature_ws', TemperatureWebSocket, dict(application=self)),
            (r'/humidity_ws', HumidityWebSocket, dict(application=self)),
            (r'/static/(.*)', tornado.web.StaticFileHandler, {'path': self.config.static_path}),
        ], template_path=self.config.template_path, debug=True)

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
    def initialize(self, template_loader, app):
        self.template_loader = template_loader
        self.app = app

    async def get(self):
        try:
            template = self.template_loader.load("index.html")
            self.write(template.generate(
                temperature_value=self.app.temperature_value,
                humidity_value=self.app.humidity_value
            ))
        except Exception as e:
            Logger.error(f"Error loading template: {e}")
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