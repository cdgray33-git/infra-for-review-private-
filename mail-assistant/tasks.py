"""
tasks.py - worker-executed tasks for mail_assistant.
"""
import os
import json
import time
import requests
import subprocess
from pathlib import Path

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3")
FLOWISE_RUN_URL = os.environ.get("FLOWISE_RUN_URL", "http://flowise:3000/api/v1/flows/run")
PERSISTENT_DIR = Path(os.environ.get("PERSISTENT_DIR", "/app/persistent"))

(PERSISTENT_DIR / "agents").mkdir(parents=True, exist_ok=True)

def call_ollama(prompt, max_tokens=512, temperature=0.0, timeout=120):
    url = f"{OLLAMA_HOST}/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()

def call_flowise(flow_id, input_data, timeout=120):
    if not flow_id:
        raise ValueError("flow_id required for call_flowise")
    payload = {"flow_id": flow_id, "input": input_data}
    resp = requests.post(FLOWISE_RUN_URL, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()

def write_agent_state(agent_dir: Path, data: dict):
    (agent_dir / "state.json").write_text(json.dumps(data, indent=2))

def append_agent_log(agent_dir: Path, line: str):
    with (agent_dir / "log.txt").open("a") as f:
        f.write(line.rstrip() + "\n")

def run_tool_adapter(agent_dir: Path, adapter_name: str, params: dict):
    adapter_path = Path("/app/tools") / adapter_name
    if not adapter_path.exists():
        append_agent_log(agent_dir, f"Adapter not found: {adapter_name}")
        raise FileNotFoundError(f"Adapter not found: {adapter_name}")

    proc = subprocess.run([str(adapter_path)], input=json.dumps(params).encode("utf-8"),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
    stdout = proc.stdout.decode("utf-8", errors="ignore")
    stderr = proc.stderr.decode("utf-8", errors="ignore")
    return {"returncode": proc.returncode, "stdout": stdout, "stderr": stderr}

def run_agent_background(agent_id: str):
    agent_dir = PERSISTENT_DIR / "agents" / agent_id
    try:
        append_agent_log(agent_dir, f"[{time.asctime()}] Agent started")
        write_agent_state(agent_dir, {"status": "running", "progress": 0})

        input_path = agent_dir / "input.json"
        if not input_path.exists():
            raise RuntimeError("input.json missing for agent " + agent_id)
        payload = json.loads(input_path.read_text())

        flow_id = payload.get("flow_id")
        if flow_id:
            append_agent_log(agent_dir, f"[{time.asctime()}] Calling Flowise flow {flow_id}")
            try:
                flow_out = call_flowise(flow_id, payload.get("context", {}))
                append_agent_log(agent_dir, f"[{time.asctime()}] Flowise responded")
            except Exception as e:
                append_agent_log(agent_dir, f"[{time.asctime()}] Flowise failed: {e}")
                flow_out = {"error": str(e)}
        else:
            flow_out = None

        prompt = payload.get("prompt") or payload.get("task") or "No task provided"
        if flow_out and isinstance(flow_out, dict):
            prompt = f"{prompt}\n\nFlowise output context:\n{json.dumps(flow_out)}"

        append_agent_log(agent_dir, f"[{time.asctime()}] Calling Ollama")
        gen = call_ollama(prompt)
        append_agent_log(agent_dir, f"[{time.asctime()}] Ollama responded")

        out = {
            "model_response": gen,
            "flowise": flow_out,
            "completed_at": time.asctime()
        }

        if payload.get("tool"):
            adapter = payload["tool"].get("name")
            params = payload["tool"].get("params", {})
            append_agent_log(agent_dir, f"[{time.asctime()}] Running adapter {adapter}")
            try:
                adapter_result = run_tool_adapter(agent_dir, adapter, params)
                out["adapter_result"] = adapter_result
                append_agent_log(agent_dir, f"[{time.asctime()}] Adapter finished rc={adapter_result.get('returncode')}")
            except Exception as e:
                append_agent_log(agent_dir, f"[{time.asctime()}] Adapter failed: {e}")
                out["adapter_error"] = str(e)

        (agent_dir / "output.json").write_text(json.dumps(out, indent=2))
        write_agent_state(agent_dir, {"status": "completed", "progress": 100})
        append_agent_log(agent_dir, f"[{time.asctime()}] Agent completed")
    except Exception as e:
        write_agent_state(agent_dir, {"status": "failed", "progress": 0, "error": str(e)})
        append_agent_log(agent_dir, f"[{time.asctime()}] Agent failed: {e}")
        raise