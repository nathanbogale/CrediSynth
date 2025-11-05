#!/usr/bin/env bash
set -euo pipefail

# Convenience wrapper so you can run ./manage.sh start|stop|restart
# It forwards to scripts/manage.sh with sensible defaults.

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_PATH="$ROOT_DIR/scripts/manage.sh"

usage() {
  cat <<EOF
Usage: ./manage.sh [start|stop|restart|status|logs|test] [--port PORT]

Examples:
  ./manage.sh start
  ./manage.sh restart --port 4010
  ./manage.sh status

Advanced:
  ./manage.sh --mode docker start
  ./manage.sh --mode docker build

This is a thin wrapper over scripts/manage.sh.
EOF
}

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "Error: $SCRIPT_PATH not found." >&2
  exit 1
fi

# If first arg is one of the simple actions, translate to --action
ACTION=""
if [[ $# -gt 0 ]]; then
  case "$1" in
    start|stop|restart|status|logs|test)
      ACTION="$1"
      shift
      ;;
    -h|--help)
      usage; exit 0 ;;
  esac
fi

# Default to local mode unless user explicitly passes --mode docker
if [[ -n "$ACTION" ]]; then
  exec "$SCRIPT_PATH" --mode local --action "$ACTION" "$@"
else
  # Pass-through for advanced usage (e.g., --mode docker ...)
  exec "$SCRIPT_PATH" "$@"
fi