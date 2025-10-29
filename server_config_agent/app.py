import os
import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="server_config_agent (minimal)")

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/action")
async def action(req: Request):
    """
    Minimal, safe placeholder for server actions. Expects JSON body like:
    {"action":"restart-service","service":"webui"} or arbitrary JSON.
    For safety this only logs and returns what it would do.
    In production replace with safe implementations.
    """
    payload = await req.json()
    return JSONResponse({"status": "accepted", "note": "dry-run placeholder", "payload": payload})
