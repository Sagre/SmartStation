cmake_minimum_required(VERSION 3.5)
project(mqtt_ros2_bridge)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)

ament_python_install_package(mqtt_ros2_bridge)

ament_package()

install(PROGRAMS
	scripts/mqtt_ros2_bridge
	DESTINATION lib/${PROJECT_NAME}
)
