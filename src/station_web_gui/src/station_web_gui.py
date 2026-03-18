#!/usr/bin/python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64
from flask import Flask, render_template

app = Flask(__name__)
temperature_value = None  # Store the temperature value

class TemperatureSubscriber(Node):
    def __init__(self):
        super().__init__('temperature_subscriber')
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

@app.route("/")
def index():
    global temperature_value
    return render_template('index.html', temperature=temperature_value)

def main(args=None):
    rclpy.init(args=args)
    temperature_subscriber = TemperatureSubscriber()
    # Create a separate thread to run the Flask app
    import threading
    flask_thread = threading.Thread(target=lambda: app.run(debug=True, host='0.0.0.0', use_reloader=False))
    flask_thread.daemon = True  # Allows the program to exit if only the flask thread remains
    flask_thread.start()

    rclpy.spin(temperature_subscriber)
    temperature_subscriber.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
