from setuptools import setup

package_name = 'station_mqtt_bridge'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    package_dir={'': 'src'},
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools', 'paho-mqtt'],
    zip_safe=True,
    maintainer='sagre',
    maintainer_email='daniel@habering.de',
    description='MQTT ROS2 bridge',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'station_mqtt_bridge = station_mqtt_bridge.station_mqtt_bridge:main',
        ],
    },
)
