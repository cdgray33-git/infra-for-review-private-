#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="docker-compose.openwebui.yml"
TMUX_SESSION="openwebui_port3033"
LOGFILE="/tmp/openwebui_port3033.log"

# Start the compose stack inside a tmux session and capture logs to file
tmux new-session -d -s $TMUX_SESSION "docker compose -f $COMPOSE_FILE up; bash"
# Wait for container to start
sleep 4
# Capture logs to a file
docker compose -f $COMPOSE_FILE logs --no-color > "$LOGFILE" 2>&1 &
echo "Started Open WebUI on http://<host>:3033 and logging to $LOGFILE"
