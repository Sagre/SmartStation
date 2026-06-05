from setuptools import setup
import os
from glob import glob

package_name = 'station_web_gui'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        
        # Include all files in the templates folder
        ('share/' + package_name + '/templates', glob('templates/*.html')),
        
        # Include all files in the static folder
        ('share/' + package_name + '/static', glob('static/*.css')),
        
        # Install the package executable under lib/<package_name> for ros2 run
        ('lib/' + package_name, ['scripts/station_web_gui']),
    ],
    install_requires=['setuptools', 'tornado', 'websockets', 'PyYAML'],
    zip_safe=True,
    maintainer='SmartStation',
    maintainer_email='devnull@example.com',
    description='ROS2 package for a web GUI showing sensor data from SmartStation devices',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'station_web_gui = station_web_gui.station_web_gui:main',
        ],
    },
)
