#!/usr/bin/env python3
import rclpy
from rclpy.node import Node

class StationLogger(Node):
    def __init__(self):
        super().__init__('station_logger')
        self.get_logger().info('Station Logger node started')

def main(args=None):
    rclpy.init(args=args)
    station_logger = StationLogger()
    try:
        rclpy.spin(station_logger)
    except KeyboardInterrupt:
        pass
    finally:
        station_logger.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()