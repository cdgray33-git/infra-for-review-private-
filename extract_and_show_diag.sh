#!/usr/bin/env bash
# One-shot: find the most recent infra diag tarball in /tmp, extract it to a temp dir,
# and print the key pieces (summary, rq_dashboard logs, agent_ui logs, and backend files).
# Run this from anywhere. Output is printed to stdout for easy copy/paste.
set -euo pipefail

# find most recent diag tarball
TARBALL="$(ls -1t /tmp/infra_diag_*.tar.gz 2>/dev/null | head -n1 || true)"
if [ -z "$TARBALL" ]; then
  echo "No /tmp/infra_diag_*.tar.gz tarball found. Listing /tmp for reference:"
  ls -lh /tmp | sed -n '1,200p'
  exit 1
fi

echo "Found tarball: $TARBALL"
TS_DIR="/tmp/diag_extract_$(date +%Y%m%dT%H%M%S)"
sudo mkdir -p "$TS_DIR"
echo "Extracting to: $TS_DIR"
sudo tar -xzf "$TARBALL" -C "$TS_DIR"

# try to detect extracted top-level dir
TOPDIR="$(sudo find "$TS_DIR" -maxdepth 1 -mindepth 1 -type d | head -n1 || true)"
if [ -z "$TOPDIR" ]; then
  # maybe files extracted directly into TS_DIR
  TOPDIR="$TS_DIR"
fi

echo
echo "=== Contents of extracted dir ($TOPDIR) ==="
sudo find "$TOPDIR" -maxdepth 2 -type f -printf "%P\n" | sed -n '1,400p' || true
echo

# Print summary.txt head if present
SUMMARY="$TOPDIR/summary.txt"
if sudo [ -f "$SUMMARY" ]; then
  echo "=== summary.txt (first 200 lines) ==="
  sudo sed -n '1,200p' "$SUMMARY" || true
  echo
else
  echo "No summary.txt found in $TOPDIR"
fi

# Print rq_dashboard logs if present
RQ_LOGS_CAND="$TOPDIR/rq_dashboard_logs.txt"
if sudo [ -f "$RQ_LOGS_CAND" ]; then
  echo "=== rq_dashboard_logs.txt (last 200 lines) ==="
  sudo tail -n 200 "$RQ_LOGS_CAND" || true
  echo
else
  echo "No rq_dashboard_logs.txt inside archive. Will attempt to fetch from docker compose logs instead."
  echo "=== Live docker compose logs --tail 200 rq_dashboard ==="
  sudo docker compose logs --tail 200 rq_dashboard 2>/tmp/rq_dashboard_compose_log.err || true
  sudo sed -n '1,200p' /tmp/rq_dashboard_compose_log.err || true
  sudo docker compose logs --tail 200 rq_dashboard || true
  echo
fi

# Print agent_ui logs if present
AGENT_LOGS_CAND="$TOPDIR/agent_ui_logs.txt"
if sudo [ -f "$AGENT_LOGS_CAND" ]; then
  echo "=== agent_ui_logs.txt (last 200 lines) ==="
  sudo tail -n 200 "$AGENT_LOGS_CAND" || true
  echo
else
  echo "No agent_ui_logs.txt inside archive. Will attempt to fetch from docker compose logs instead."
  echo "=== Live docker compose logs --tail 200 agent_ui ==="
  sudo docker compose logs --tail 200 agent_ui 2>/tmp/agent_ui_compose_log.err || true
  sudo sed -n '1,200p' /tmp/agent_ui_compose_log.err || true
  sudo docker compose logs --tail 200 agent_ui || true
  echo
fi

# Print server_config_agent logs if present
SCA_LOGS="$TOPDIR/server_config_agent_logs.txt"
if sudo [ -f "$SCA_LOGS" ]; then
  echo "=== server_config_agent_logs.txt (last 200 lines) ==="
  sudo tail -n 200 "$SCA_LOGS" || true
  echo
fi

# Show last ~300 lines of backend files if present in repo (relative paths)
echo "=== Checking local agent-ui/backend files (if present) ==="
if [ -f "agent-ui/backend/main.py" ]; then
  echo "---- agent-ui/backend/main.py (first 300 lines) ----"
  sed -n '1,300p' agent-ui/backend/main.py || true
  echo
else
  echo "agent-ui/backend/main.py not found in repo working dir."
fi

if [ -f "agent-ui/backend/agent-ui_backend_main_Version2.py" ]; then
  echo "---- agent-ui/backend/agent-ui_backend_main_Version2.py (first 300 lines) ----"
  sed -n '1,300p' agent-ui/backend/agent-ui_backend_main_Version2.py || true
  echo
else
  echo "agent-ui/backend/agent-ui_backend_main_Version2.py not found in repo working dir."
fi

# If there are any captured backend files inside the extracted dir, show tails
for f in "$TOPDIR"/agent_ui* "$TOPDIR"/agent-ui* "$TOPDIR"/agent_ui_logs.txt "$TOPDIR"/agent-ui*  ; do
  [ -e "$f" ] || continue
  echo "=== Extracted file: $f (tail 200) ==="
  sudo tail -n 200 "$f" || true
  echo
done

echo "=== Done. Extracted contents are under: $TOPDIR ==="
echo "If you want to share logs, copy/paste the printed sections above. If you prefer, upload $TARBALL or the extracted directory to a share and paste the link."