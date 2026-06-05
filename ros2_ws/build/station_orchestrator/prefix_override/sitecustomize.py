import sys
if sys.prefix == '/usr':
    sys.real_prefix = sys.prefix
    sys.prefix = sys.exec_prefix = '/home/sagre/SmartStationNew/ros2_ws/install/station_orchestrator'
