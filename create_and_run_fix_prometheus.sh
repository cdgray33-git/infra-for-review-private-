#!/usr/bin/env bash
# One-shot: backup mistaken prometheus.yml dir, write a proper prometheus.yml file,
# then build & bring up the docker-compose stack and print status + logs for debugging.
# Run from project root (the directory containing docker-compose.yml).
set -euo pipefail

echo "Working directory: $(pwd)"
echo "Checking for existing prometheus.yml..."

if [ -e prometheus.yml ] ; then
  if [ -d prometheus.yml ] ; then
    echo "prometheus.yml exists and is a directory. Backing it up to prometheus.yml.dir.bak..."
    sudo mv -v prometheus.yml prometheus.yml.dir.bak
    echo "Backup created: prometheus.yml.dir.bak"
  else
    echo "prometheus.yml is a file (will be overwritten). Backing up to prometheus.yml.bak..."
    sudo cp -a prometheus.yml prometheus.yml.bak
    echo "Backup created: prometheus.yml.bak"
  fi
else
  echo "No existing prometheus.yml found. Proceeding to create one."
fi

echo "Writing new prometheus.yml (minimal) ..."
sudo tee prometheus.yml > /dev/null <<'EOF'
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'agent_ui'
    metrics_path: /metrics
    static_configs:
      - targets: ['agent_ui:80']

  - job_name: 'mail_assistant'
    metrics_path: /metrics
    static_configs:
      - targets: ['mail_assistant:8002']
EOF

echo "Set permissions and ownership for prometheus.yml"
sudo chown root:root prometheus.yml || true
sudo chmod 644 prometheus.yml || true

echo
echo "Validating docker-compose config..."
if sudo docker compose config >/dev/null 2>&1; then
  echo "docker-compose config OK"
else
  echo "docker-compose config FAILED. Printing compose config output:"
  sudo docker compose config || true
  echo "Aborting before starting containers."
  exit 1
fi

echo
echo "Bringing up the compose stack (build & start) -- this may take a few minutes..."
sudo docker compose up -d --build

echo
echo "Waiting 6 seconds for containers to initialize..."
sleep 6

echo
echo "=== docker compose ps ==="
sudo docker compose ps

echo
echo "=== Tail logs (agent_ui, prometheus, rq-proxy, server_config_agent) ==="
echo "------ agent_ui ------"
sudo docker compose logs --tail 200 agent_ui || true
echo "------ prometheus ------"
sudo docker compose logs --tail 200 prometheus || true
echo "------ rq-proxy ------"
sudo docker compose logs --tail 200 rq-proxy || true
echo "------ server_config_agent ------"
sudo docker compose logs --tail 200 server_config_agent || true

echo
echo "If any service is restarting or failing, copy the logs from above and paste them here and I will help diagnose further."