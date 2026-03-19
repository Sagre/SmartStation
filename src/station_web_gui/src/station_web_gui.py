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
import asyncio  # Import asyncio

class HomeHandler(tornado.web.RequestHandler):
    def initialize(self, template_loader):
        self.template_loader = template_loader

    async def get(self):
        try:
            template = self.template_loader.load("index.html")
            self.write(template.generate(temperature_value=self.application.temperature_value,
                                        humidity_value=self.application.humidity_value))
        except Exception as e:
            self.set_status(500)
            self.write(f"Error loading template: {e}")

class TemperatureWebSocket(tornado.websocket.WebSocketHandler):
    def initialize(self):
        self.temperature = 25
        self.last_update = 0

    def open(self):
        print("Temperature WebSocket opened")
        # Store reference to this handler in the app
        self.application.temperature_ws_handler = self

    def on_close(self):
        print("Temperature WebSocket closed")
        # Clear reference when closed
        if self.application.temperature_ws_handler == self:
            self.application.temperature_ws_handler = None

    def on_message(self, message):
        pass

    async def get_latest_value(self):
        return self.temperature

    async def update_temperature(self, value):
        self.temperature = value
        self.last_update = tornado.ioloop.IOLoop.current().time()
        self.write_message(json.dumps({"temperature": self.temperature}))


class HumidityWebSocket(tornado.websocket.WebSocketHandler):
    def initialize(self):
        self.humidity = 60
        self.last_update = 0

    def open(self):
        print("Humidity WebSocket opened")
        # Store reference to this handler in the app
        self.application.humidity_ws_handler = self

    def on_close(self):
        print("Humidity WebSocket closed")
        # Clear reference when closed
        if self.application.humidity_ws_handler == self:
            self.application.humidity_ws_handler = None

    def on_message(self, message):
        pass

    async def get_latest_value(self):
        return self.humidity

    async def update_humidity(self, value):
        self.humidity = value
        self.last_update = tornado.ioloop.IOLoop.current().time()
        self.write_message(json.dumps({"humidity": self.humidity}))

class ROS2Bridge(Node):
    def __init__(self, app):
        super().__init__('ros2_web_bridge')
        self.app = app # Reference to the Tornado application
        self.temperature_value = 25
        self.humidity_value = 60
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
        self.get_logger().info('ROS2 Bridge Node started')

    def temperature_callback(self, msg):
        self.temperature_value = msg.data
        self.get_logger().info(f"Received temperature: {self.temperature_value}")
        self.update_temperature_web_sockets()

    def humidity_callback(self, msg):
        self.humidity_value = msg.data
        self.get_logger().info(f"Received humidity: {self.humidity_value}")
        self.update_humidity_web_sockets()

    def update_temperature_web_sockets(self):
        if self.app.temperature_ws_handler:
            try:
                self.app.temperature_ws_handler.write_message(json.dumps({"temperature": self.temperature_value}))
            except Exception as e:
                self.get_logger().error(f"Error sending temperature to WebSocket: {e}")

    def update_humidity_web_sockets(self):
        if self.app.humidity_ws_handler:
            try:
                self.app.humidity_ws_handler.write_message(json.dumps({"humidity": self.humidity_value}))
            except Exception as e:
                self.get_logger().error(f"Error sending humidity to WebSocket: {e}")

def make_app(template_path, static_path):
    app = tornado.web.Application([
        (r"/", HomeHandler),
        (r"/temperature_ws", TemperatureWebSocket),
        (r"/humidity_ws", HumidityWebSocket),
        (r"/static/(.*)", tornado.web.StaticFileHandler, {'path': static_path}), #Add static path
    ], template_path=template_path, debug=True)
    app.temperature_value = 25
    app.humidity_value = 60
    app.temperature_ws_handler = None
    app.humidity_ws_handler = None
    return app

def main(args=None):
    rclpy.init(args=args)

    # Get the current file's directory
    file_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(file_dir, "templates")
    static_path = os.path.join(file_dir, "static") # Get static path

    # Create and start the Tornado application in a separate thread
    app = make_app(template_path, static_path)

    # Create and start the ROS2 Bridge in a separate thread
    def start_ros2_bridge():
        nonlocal app
        ros2_bridge_node = ROS2Bridge(app)
        rclpy.spin(ros2_bridge_node)
        # Clean up
        ros2_bridge_node.destroy_node()
        rclpy.shutdown()

    # Get the IOLoop instance
    ioloop = tornado.ioloop.IOLoop.current()

    # Create a new thread for ROS2
    ros2_thread = threading.Thread(target=start_ros2_bridge, daemon=True)
    ros2_thread.start()

    def start_tornado():
        port = 8888  # Or any port you want
        app.listen(port)
        ioloop.start()
        print(f"Tornado server started on port {port}")

    tornado_thread = threading.Thread(target=start_tornado, daemon=True)
    tornado_thread.start()

    print("Server listening on port 8888")
    # Keep the main thread alive (for the web server)
    # ioloop.start() #The ioloop is already handled in the 'start_tornado' function
    ioloop.add_callback(lambda: print("Tornado Ready!"))
    rclpy.spin(TemperatureSubscriber)

    print("Shutting down")
    ioloop.stop() #Shut down the IOLoop
    rclpy.shutdown()

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main()