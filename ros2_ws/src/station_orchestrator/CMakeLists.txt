cmake_minimum_required(VERSION 3.5)
project(station_orchestrator)

find_package(ament_cmake_python REQUIRED)
ament_python_install_package(${PROJECT_NAME})

install(
  DIRECTORY resource
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
