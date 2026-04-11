from setuptools import setup

package_name = 'station_core'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    package_dir={'': 'src'},
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools', 'PyYAML'],
    zip_safe=True,
    maintainer='sagre',
    maintainer_email='daniel@habering.de',
    description='Core ROS2 package for SmartStation',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'station_core = station_core.station_core:main',
        ],
    },
)