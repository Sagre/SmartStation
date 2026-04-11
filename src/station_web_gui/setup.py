from setuptools import setup
import os
from glob import glob

package_name = 'station_web_gui'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    package_dir={'': 'src'},
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        
        # Include all files in the templates folder
        ('share/' + package_name + '/templates', glob('templates/*.html')),
        
        # Include all files in the static folder
        ('share/' + package_name + '/static', glob('static/*.css')),
    ],
    install_requires=['setuptools', 'tornado', 'websockets', 'PyYAML'],
    zip_safe=True,
    maintainer='Your Name',
    maintainer_email='your_email@example.com',
    description='ROS2 package for a Tornado web GUI',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'station_web_gui = station_web_gui.station_web_gui:main',
            'sensor_publisher = station_web_gui.sensor_publisher:main',
        ],
    },
)