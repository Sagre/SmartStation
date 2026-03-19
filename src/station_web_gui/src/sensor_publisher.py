#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64
import random
import time

class SensorPublisher(Node):
    def __init__(self):
        super().__init__('sensor_publisher')
        self.temperature_publisher = self.create_publisher(Float64, 'temperature', 10)
        self.humidity_publisher = self.create_publisher(Float64, 'humidity', 10)
        timer_period = 2  # seconds
        self.timer = self.create_timer(timer_period, self.timer_callback)
        self.i = 0

    def timer_callback(self):
        temperature_msg = Float64()
        temperature_msg.data = 20.0 + random.uniform(-2, 5)  # Example
        self.temperature_publisher.publish(temperature_msg)
        self.get_logger().info('Publishing temperature: "%f"' % temperature_msg.data)

        humidity_msg = Float64()
        humidity_msg.data = 60.0 + random.uniform(-5, 5)  # Example
        self.humidity_publisher.publish(humidity_msg)
        self.get_logger().info('Publishing humidity: "%f"' % humidity_msg.data)
        self.i += 1

def main(args=None):
    rclpy.init(args=args)
    sensor_publisher = SensorPublisher()
    rclpy.spin(sensor_publisher)
    # Destroy the node explicitly
    # (optional - otherwise it will be done automatically
    # when the garbage collector destroys the node object)
    sensor_publisher.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()