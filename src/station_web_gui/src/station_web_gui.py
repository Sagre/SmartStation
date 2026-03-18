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

temperature_value = None  # Store the temperature value

class TemperatureSubscriber(Node):
    def __init__(self, websocket_handler):
        super().__init__('temperature_subscriber')
        self.websocket_handler = websocket_handler
        self.subscription = self.create_subscription(
            Float64,
            'temperature',
            self.listener_callback,
            10)
        self.subscription  # prevent unused variable warning
        self.get_logger().info('Temperature Subscriber Node started')

    def listener_callback(self, msg):
        global temperature_value
        temperature_value = msg.data
        self.get_logger().info(f'Received temperature: {temperature_value}')
        # Send to WebSocket if connected
        if self.websocket_handler and self.websocket_handler.ws_connection:
            try:
                self.websocket_handler.write_message(json.dumps({'temperature': temperature_value}))
            except Exception as e:
                self.get_logger().error(f"Error sending message to websocket: {e}")

class IndexHandler(tornado.web.RequestHandler):
    def initialize(self, template_loader):
        self.template_loader = template_loader

    def get(self):
        global temperature_value
        try:
            template = self.template_loader.load("index.html")
            self.write(template.generate(temperature=temperature_value))
        except Exception as e:
            self.set_status(500)
            self.write(f"Error loading template: {e}")


class WebSocketHandler(tornado.websocket.WebSocketHandler):
    def initialize(self):
        self.temperature_subscriber = None  # Store a reference to the subscriber

    def open(self):
        print("WebSocket opened")

    def on_message(self, message):
        print(f"Received message: {message}")

    def on_close(self):
        print("WebSocket closed")
        # Cleanup when the WebSocket closes:
        if self.temperature_subscriber:
            rclpy.shutdown()  # Shut down ROS2 if no longer needed

    def set_subscriber(self, subscriber):
      self.temperature_subscriber = subscriber # sets the subscriber

def main(args=None):
    rclpy.init(args=args)

    # Prepare for Tornado
    settings = {
        "template_path": os.path.join(os.path.dirname(__file__), "templates"),
        "static_path": os.path.join(os.path.dirname(__file__), "static"), # Add static path
        "debug": True,
    }

    # Instantiate the WebSocket Handler
    websocket_handler = WebSocketHandler()

    # Create the Temperature Subscriber, passing it the websocket_handler
    temperature_subscriber = TemperatureSubscriber(websocket_handler)

    # Set the subscriber in the handler
    websocket_handler.set_subscriber(temperature_subscriber)

    template_loader = tornado.template.Loader(os.path.join(os.path.dirname(__file__), "templates"))

    # Create and start the Tornado application in a separate thread
    app = tornado.web.Application([
        (r'/', IndexHandler, dict(template_loader=template_loader)),  # Root path
        (r'/ws', WebSocketHandler),  # WebSocket endpoint
    ], **settings)

    def start_tornado():
        port = 8888  # Or any port you want
        app.listen(port)
        tornado.ioloop.IOLoop.current().start()
        print(f"Tornado server started on port {port}")


    tornado_thread = threading.Thread(target=start_tornado)
    tornado_thread.daemon = True # Allow the main thread to exit
    tornado_thread.start()

    rclpy.spin(temperature_subscriber)
    temperature_subscriber.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()