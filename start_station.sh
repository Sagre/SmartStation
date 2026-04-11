#!/usr/bin/env bash
set -euo pipefail

# SmartStation single-entry startup script.
# Builds nothing by default; assumes the workspace has already been built.

cd "$(dirname "$0")"
colcon build --packages-select station_core station_mqtt_bridge station_web_gui

if [ -f install/setup.bash ]; then
  # Source ROS/colcon setup without `set -u` causing unbound variable failures.
  set +u
  # shellcheck source=/dev/null
  source install/setup.bash
  set -u
else
  echo "ERROR: install/setup.bash not found. Build the workspace first."
  exit 1
fi

station_core_exec="$(pwd)/install/station_core/bin/station_core"
if [ -x "$station_core_exec" ]; then
  exec "$station_core_exec" "$@"
fi

exec ros2 run station_core station_core "$@"
