from setuptools import setup

package_name = 'station_web_gui'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    py_modules=[],
    install_requires=['setuptools', 'flask'],  # <--- Important! Declare dependencies here
    zip_safe=True,
    author='Your Name',
    author_email='your_email@example.com',
    maintainer='Your Name',
    maintainer_email='your_email@example.com',
    keywords=['ROS2', 'Flask', 'Web GUI'],
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
    ],
    description='ROS2 package for a Flask web GUI showing temperature.',
    license='TODO: License declaration',
    entry_points={
        'console_scripts': [
            'station_web_gui = station_web_gui.station_web_gui:main', # Replace with the correct module and entry point
        ],
    },
)
