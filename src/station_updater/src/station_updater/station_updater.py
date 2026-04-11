#!/usr/bin/env python3
import rclpy
from rclpy.node import Node

class StationUpdater(Node):
    def __init__(self):
        super().__init__('station_updater')
        self.get_logger().info('Station Updater node started')


def main(args=None):
    rclpy.init(args=args)
    station_updater = StationUpdater()
    try:
        rclpy.spin(station_updater)
    except KeyboardInterrupt:
        pass
    finally:
        station_updater.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()