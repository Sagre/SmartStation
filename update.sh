git pull
colcon build --packages-select station_web_gui
source install/setup.bash
ros2 run station_web_gui station_web_gui.py
