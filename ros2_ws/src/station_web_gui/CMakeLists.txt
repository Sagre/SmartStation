cmake_minimum_required(VERSION 3.8)
project(station_web_gui)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_COMPILER_IS_CLANGXX)
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)

ament_python_install_package(${PROJECT_NAME})

install(PROGRAMS
  scripts/station_web_gui
  DESTINATION lib/${PROJECT_NAME}
)

install(
  DIRECTORY
    static/
    templates/
  DESTINATION share/station_web_gui
)

ament_package()
