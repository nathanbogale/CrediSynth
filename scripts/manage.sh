#!/usr/bin/env bash
set -euo pipefail

# Defaults
MODE="local"          # local | docker
ACTION="start"        # build | start | stop | restart | status | logs | test
ENV_FILE=".env"
TAG="credisynth-qaa:local"
CONTAINER="credisynth-qaa"
PORT="7000"

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOGS_DIR="$ROOT_DIR/logs"
PID_FILE="$LOGS_DIR/.local_api.pid"
LOG_FILE="$LOGS_DIR/local_server.log"

mkdir -p "$LOGS_DIR"

usage() {
  cat <<EOF
Usage: manage.sh [--mode local|docker] [--action build|start|stop|restart|status|logs|test] [--env-file PATH] [--tag TAG] [--container NAME] [--port PORT]

Examples:
  ./scripts/manage.sh --mode local --action start
  ./scripts/manage.sh --mode local --action logs
  ./scripts/manage.sh --mode docker --action build
  ./scripts/manage.sh --mode docker --action start
  ./scripts/manage.sh --action test
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) MODE="$2"; shift 2 ;;
    --action) ACTION="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --tag) TAG="$2"; shift 2 ;;
    --container) CONTAINER="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1"; usage; exit 1 ;;
  esac
done

ensure_venv() {
  if [[ -x "$ROOT_DIR/.venv/bin/uvicorn" ]]; then
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    PY="python3"
  elif command -v python >/dev/null 2>&1; then
    PY="python"
  else
    echo "Python not found. Please install Python 3.11+" >&2
    exit 1
  fi
  echo "Creating virtual environment..."
  "$PY" -m venv "$ROOT_DIR/.venv"
  echo "Installing dependencies..."
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.venv/bin/activate"
  pip install -r "$ROOT_DIR/requirements.txt"
}

start_local() {
  ensure_venv
  echo "Starting local API on port $PORT"
  # shellcheck disable=SC1091
  nohup bash -c "source \"$ROOT_DIR/.venv/bin/activate\" && uvicorn app.main:app --host 0.0.0.0 --port $PORT --reload" >"$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  echo "Started. PID: $(cat "$PID_FILE") Logs: $LOG_FILE"
}

stop_local() {
  if [[ ! -f "$PID_FILE" ]]; then
    echo "No local PID file found."
    return
  fi
  PID="$(head -n1 "$PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" || true
    rm -f "$PID_FILE"
    echo "Stopped local API (PID $PID)."
  else
    echo "Process $PID not running."
    rm -f "$PID_FILE"
  fi
}

status_local() {
  if [[ -f "$PID_FILE" ]] && kill -0 "$(head -n1 "$PID_FILE")" 2>/dev/null; then
    echo "Local API: running (PID $(head -n1 "$PID_FILE"))"
  else
    echo "Local API: not running"
  fi
}

logs_local() {
  if [[ ! -f "$LOG_FILE" ]]; then
    echo "No log file yet: $LOG_FILE"
    return
  fi
  echo "Tailing $LOG_FILE (Ctrl+C to stop)"
  tail -f "$LOG_FILE"
}

build_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker CLI not found" >&2
    exit 1
  fi
  echo "Building Docker image $TAG"
  docker build -t "$TAG" "$ROOT_DIR"
}

start_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker CLI not found" >&2
    exit 1
  fi
  echo "Starting Docker container $CONTAINER on port $PORT"
  docker run -d --name "$CONTAINER" -p "$PORT:$PORT" --env-file "$ROOT_DIR/$ENV_FILE" "$TAG"
}

stop_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker CLI not found" >&2
    exit 1
  fi
  docker stop "$CONTAINER" >/dev/null 2>&1 || true
  docker rm "$CONTAINER" >/dev/null 2>&1 || true
  echo "Stopped and removed container $CONTAINER"
}

status_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker CLI not found" >&2
    exit 1
  fi
  docker ps -a --filter "name=$CONTAINER" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
}

logs_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker CLI not found" >&2
    exit 1
  fi
  docker logs -f "$CONTAINER"
}

test_api() {
  BASE_URL="http://127.0.0.1:$PORT"
  echo "Health: $BASE_URL/health"
  curl -sS "$BASE_URL/health" || true
  echo
  echo "Analyze: $BASE_URL/v1/analyze"
  curl -sS -X POST "$BASE_URL/v1/analyze" -H "Content-Type: application/json" --data @"$ROOT_DIR/sample_request.json" || true
  echo
}

case "$MODE" in
  local)
    case "$ACTION" in
      build) ensure_venv ;;
      start) start_local ;;
      stop) stop_local ;;
      restart) stop_local; start_local ;;
      status) status_local ;;
      logs) logs_local ;;
      test) test_api ;;
      *) echo "Unknown action: $ACTION"; usage; exit 1 ;;
    esac
    ;;
  docker)
    case "$ACTION" in
      build) build_docker ;;
      start) start_docker ;;
      stop) stop_docker ;;
      restart) stop_docker; start_docker ;;
      status) status_docker ;;
      logs) logs_docker ;;
      test) test_api ;;
      *) echo "Unknown action: $ACTION"; usage; exit 1 ;;
    esac
    ;;
  *)
    echo "Unknown mode: $MODE"
    usage
    exit 1
    ;;
esac