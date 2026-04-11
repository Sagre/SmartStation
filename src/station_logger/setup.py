from setuptools import setup

package_name = 'station_logger'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    package_dir={'': 'src'},
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='sagre',
    maintainer_email='daniel@habering.de',
    description='ROS2 logging package for SmartStation',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'station_logger = station_logger.station_logger:main',
        ],
    },
)