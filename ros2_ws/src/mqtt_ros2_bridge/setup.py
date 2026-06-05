from setuptools import setup
import os
from glob import glob

package_name = 'mqtt_ros2_bridge'

setup(
    name=package_name,
    version='0.1.0',
    packages=["mqtt_ros2_bridge"],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='SmartStation',
    maintainer_email='devnull@example.com',
    description='MQTT to ROS2 bridge for SmartStation',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'mqtt_ros2_bridge = mqtt_ros2_bridge.bridge_node:main'
        ],
    },
)
