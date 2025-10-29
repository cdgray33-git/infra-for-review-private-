#!/usr/bin/env bash
# One-shot script: create/repair three files and bring up the compose stack.
# Usage: copy/paste and run from the project root (./infra-agent)
set -euo pipefail
echo "=== Creating directories ==="
sudo mkdir -p agent-ui/backend rq-proxy

echo "=== Writing agent-ui/backend/main.py (wrapper) ==="
sudo tee agent-ui/backend/main.py > /dev/null <<'EOF'
# Lightweight wrapper to expose the FastAPI `app` object for uvicorn:
# It loads the backend implementation from agent-ui_backend_main_Version2.py at runtime.
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = HERE / "agent-ui_backend_main_Version2.py"

if not TARGET.exists():
    raise RuntimeError(f"Expected backend implementation at {TARGET}, but file not found")

spec = importlib.util.spec_from_file_location("agent_ui_impl", str(TARGET))
module = importlib.util.module_from_spec(spec)
sys.modules["agent_ui_impl"] = module
spec.loader.exec_module(module)

# The backend file must define a FastAPI instance named `app`
try:
    app = getattr(module, "app")
except Exception as e:
    raise RuntimeError("Loaded backend module but 'app' was not found") from e
EOF

echo "=== Writing rq-proxy/app.py (reverse proxy) ==="
sudo tee rq-proxy/app.py > /dev/null <<'EOF'
# rq-proxy/app.py
# Simple reverse proxy to rq-dashboard (forwards requests to rq_dashboard:9181)
from fastapi import FastAPI, Request, Response
import httpx
import os

app = FastAPI(title="rq-proxy")

RQ_DASH_URL = os.environ.get("RQ_DASHBOARD_URL", "http://rq_dashboard:9181")

@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy(full_path: str, request: Request):
    url = f"{RQ_DASH_URL}/{full_path}"
    headers = dict(request.headers)
    headers.pop("host", None)
    body = await request.body()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request(
            method=request.method,
            url=url,
            headers=headers,
            content=body,
            params=request.query_params
        )
    # Copy back response. In production, filter hop-by-hop headers.
    response_headers = dict(resp.headers)
    return Response(content=resp.content, status_code=resp.status_code, headers=response_headers)
EOF

echo "=== Writing prometheus.yml (minimal) ==="
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

echo "=== Ensuring permissions for created files ==="
sudo chown root:root agent-ui/backend/main.py rq-proxy/app.py prometheus.yml || true
sudo chmod 644 agent-ui/backend/main.py rq-proxy/app.py prometheus.yml || true

echo "=== Building and starting docker compose stack ==="
sudo docker compose up -d --build

echo "=== Waiting a few seconds for containers to initialize ==="
sleep 6

echo "=== Compose status ==="
sudo docker compose ps

echo "=== Tail logs for key services (agent_ui, rq-proxy, server_config_agent, prometheus) ==="
echo "------ agent_ui ------"
sudo docker compose logs --tail 200 agent_ui || true
echo "------ rq-proxy ------"
sudo docker compose logs --tail 200 rq-proxy || true
echo "------ server_config_agent ------"
sudo docker compose logs --tail 200 server_config_agent || true
echo "------ prometheus ------"
sudo docker compose logs --tail 200 prometheus || true

echo "=== Done. If any service is restarting or failing, paste the logs shown above and I will help debug. ==="
EOF