#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f "$SCRIPT_DIR/install/setup.bash" ]]; then
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/install/setup.bash"
else
  echo "ROS2 workspace is not built. Run: colcon build" >&2
  exit 1
fi

exec ros2 run station_orchestrator station_orchestrator "$@"
