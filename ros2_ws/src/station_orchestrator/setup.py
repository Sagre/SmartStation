from setuptools import setup

package_name = 'station_orchestrator'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('lib/' + package_name, ['scripts/' + package_name]),
    ],
    install_requires=['setuptools', 'PyYAML'],
    zip_safe=True,
    maintainer='SmartStation',
    maintainer_email='devnull@example.com',
    description='Station orchestration node for SmartStation launch and health monitoring',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'station_orchestrator = station_orchestrator.orchestrator_node:main',
        ],
    },
)
