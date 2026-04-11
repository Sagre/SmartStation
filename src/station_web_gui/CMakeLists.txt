cmake_minimum_required(VERSION 3.8)
project(station_web_gui)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_COMPILER_IS_CLANGXX)
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_python_install_package(${PROJECT_NAME} PACKAGE_DIR src/${PROJECT_NAME})

install(
  DIRECTORY
    static/
    templates/
  DESTINATION share/station_web_gui
)

install(
  FILES
    src/station_web_gui/sensor_config.json
  DESTINATION share/station_web_gui
)

ament_package()
