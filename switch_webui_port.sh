#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="docker-compose.yml"
SERVICE="webui"
OLD_PORT="8080"
NEW_PORT="8082"

# 1. Backup the compose file
cp "$COMPOSE_FILE" "${COMPOSE_FILE}.bak"

# 2. Substitute the port mapping for 'webui' service
awk -v srv="$SERVICE" -v o="$OLD_PORT" -v n="$NEW_PORT" '
  $0 ~ "^"srv":" {in_srv=1}
  in_srv && $0 ~ "- \""o":80\"" {
    sub("- \""o":80\"", "- \""n":80\"")
    in_srv=0
  }
  {print}
' "$COMPOSE_FILE" > "${COMPOSE_FILE}.tmp"
mv "${COMPOSE_FILE}.tmp" "$COMPOSE_FILE"

echo "Switched webui port mapping from $OLD_PORT to $NEW_PORT in $COMPOSE_FILE"
echo "Bringing up webui service..."

# 3. Bring up webui on the new port
sudo docker compose up -d webui

# 4. Check running status and port mapping
sudo docker ps | grep webui

echo "You can now reach nginx on http://<your-host>:$NEW_PORT/"
echo "Previous compose file backed up as ${COMPOSE_FILE}.bak"
