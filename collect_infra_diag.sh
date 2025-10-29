#!/usr/bin/env bash
# One-shot diagnostics for infra-agent stack: collect status, logs, container state and save to /tmp.
# Run from project root (where docker-compose.yml lives).
set -euo pipefail
TS="$(date +%Y%m%dT%H%M%S)"
OUTDIR="/tmp/infra_diag_${TS}"
sudo rm -rf "${OUTDIR}"
mkdir -p "${OUTDIR}"

echo "=== Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ") ===" | tee "${OUTDIR}/summary.txt"

echo -e "\n=== docker compose version & config ===" | tee -a "${OUTDIR}/summary.txt"
sudo docker compose version >> "${OUTDIR}/summary.txt" 2>&1 || true
sudo docker compose config >> "${OUTDIR}/compose_config.txt" 2>&1 || true
tail -n +1 "${OUTDIR}/compose_config.txt" | sed -n '1,250p' >> "${OUTDIR}/summary.txt" 2>&1 || true

echo -e "\n=== docker compose ps (full) ===" | tee -a "${OUTDIR}/summary.txt"
sudo docker compose ps --all | tee "${OUTDIR}/compose_ps.txt"

echo -e "\n=== Host listening ports (ss) ===" | tee -a "${OUTDIR}/summary.txt"
sudo ss -ltnp > "${OUTDIR}/ss_listening.txt" 2>&1 || true
sudo cat "${OUTDIR}/ss_listening.txt" | sed -n '1,200p' >> "${OUTDIR}/summary.txt"

# Key service logs - adjust list below as needed
SERVICES_TO_CHECK=(rq_dashboard agent_ui mail_assistant server_config_agent rq_proxy flowise grafana prometheus)

for svc in "${SERVICES_TO_CHECK[@]}"; do
  echo -e "\n=== docker compose logs --tail 500 ${svc} ===" | tee -a "${OUTDIR}/summary.txt"
  sudo docker compose logs --tail 500 "${svc}" > "${OUTDIR}/${svc}_logs.txt" 2>&1 || true
  # show last 200 lines inline for quick review
  echo "----- tail ${svc}_logs.txt -----" >> "${OUTDIR}/summary.txt"
  tail -n 200 "${OUTDIR}/${svc}_logs.txt" >> "${OUTDIR}/summary.txt" 2>&1 || true
done

# If rq_dashboard has a container id, inspect it
RQ_ID="$(sudo docker compose ps -q rq_dashboard 2>/dev/null || true)"
if [ -n "${RQ_ID}" ]; then
  echo -e "\n=== docker inspect (rq_dashboard) ===" | tee -a "${OUTDIR}/summary.txt"
  sudo docker inspect "${RQ_ID}" > "${OUTDIR}/rq_dashboard_inspect.json" 2>&1 || true
  # capture last state and restart count
  sudo docker inspect --format '{{json .State}}' "${RQ_ID}" > "${OUTDIR}/rq_dashboard_state.json" 2>&1 || true
  echo "container id: ${RQ_ID}" | tee -a "${OUTDIR}/summary.txt"
  echo "Last container state:" >> "${OUTDIR}/summary.txt"
  jq -r '.' "${OUTDIR}/rq_dashboard_state.json" 2>/dev/null | sed -n '1,200p' >> "${OUTDIR}/summary.txt" || cat "${OUTDIR}/rq_dashboard_state.json" >> "${OUTDIR}/summary.txt" 2>&1 || true
else
  echo -e "\n=== rq_dashboard container not found via docker compose ps -q ===" | tee -a "${OUTDIR}/summary.txt"
fi

# Show recent docker events (last 5 minutes) to catch port-bind / create errors
echo -e "\n=== docker events (recent 5m) filtered for create/start/stop) ===" | tee -a "${OUTDIR}/summary.txt"
sudo timeout 1 docker events --since 5m --filter 'type=container' --format '{{json .}}' > "${OUTDIR}/docker_events_recent.json" 2>&1 || true
tail -n 200 "${OUTDIR}/docker_events_recent.json" >> "${OUTDIR}/summary.txt" 2>&1 || true

# Save docker ps -a and images
sudo docker ps -a > "${OUTDIR}/docker_ps_a.txt" 2>&1 || true
sudo docker images > "${OUTDIR}/docker_images.txt" 2>&1 || true

echo -e "\n=== Compose and container health summary ===" | tee -a "${OUTDIR}/summary.txt"
sudo docker compose ps --all >> "${OUTDIR}/summary.txt" 2>&1 || true

# Tar up the results
ARCHIVE="/tmp/infra_diag_${TS}.tar.gz"
tar -czf "${ARCHIVE}" -C /tmp "$(basename "${OUTDIR}")"

echo
echo "Diagnostics collected to: ${ARCHIVE}"
echo "You can paste the content of ${OUTDIR}/summary.txt and/or attach ${ARCHIVE}."
echo
echo "Quick helpful commands (run manually if you want immediate tail):"
echo "  sudo docker compose logs --tail 200 rq_dashboard"
echo "  sudo docker inspect <container-id> --format '{{json .State}}' | jq"
echo "  sudo docker compose up -d --no-deps --force-recreate --build rq_dashboard"
echo
echo "Script finished."