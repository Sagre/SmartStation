from setuptools import find_packages
from setuptools import setup

setup(
    name='mqtt_ros2_bridge',
    version='0.1.0',
    packages=find_packages(
        include=('mqtt_ros2_bridge', 'mqtt_ros2_bridge.*')),
)
