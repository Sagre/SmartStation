#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64
import random
import time
from typing import Optional

class SensorPublisher(Node):
    """ROS2 node for publishing sensor data."""
    def __init__(self):
        super().__init__('sensor_publisher')
        self.temperature_publisher = self.create_publisher(Float64, 'temperature', 10)
        self.humidity_publisher = self.create_publisher(Float64, 'humidity', 10)
        self.timer = self.create_timer(2.0, self.timer_callback)
        self.i = 0

    def timer_callback(self):
        """Publish random temperature and humidity values."""
        temperature_msg = Float64()
        temperature_msg.data = 20.0 + random.uniform(-2, 5)
        self.temperature_publisher.publish(temperature_msg)
        self.get_logger().info(f'Publishing temperature: {temperature_msg.data:.2f}')

        humidity_msg = Float64()
        humidity_msg.data = 60.0 + random.uniform(-5, 5)
        self.humidity_publisher.publish(humidity_msg)
        self.get_logger().info(f'Publishing humidity: {humidity_msg.data:.2f}')
        self.i += 1

def main(args=None):
    rclpy.init(args=args)
    sensor_publisher = SensorPublisher()
    rclpy.spin(sensor_publisher)
    sensor_publisher.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()