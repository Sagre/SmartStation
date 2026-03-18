cmake_minimum_required(VERSION 3.8)
project(station_web_gui)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_COMPILER_IS_CLANGXX)
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclpy REQUIRED)
find_package(std_msgs REQUIRED)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

# Install the Python script
install(
  PROGRAMS
    src/station_web_gui.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()