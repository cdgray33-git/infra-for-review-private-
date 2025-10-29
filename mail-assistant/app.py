from pathlib import Path
import os
import json
import time
import requests
import subprocess
from typing import Dict

# helpers for logging and state
from agent_logging import ensure_agent_dir, append_agent_log, write_agent_state

# Config
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")
FLOWISE_RUN_URL = os.environ.get("FLOWISE_RUN_URL", "http://flowise:3000/api/v1/flows/run")
PERSISTENT_DIR = Path(os.environ.get("PERSISTENT_DIR", "/app/persistent"))

# Ensure base agents folder exists
(PERSISTENT_DIR / "agents").mkdir(parents=True, exist_ok=True)

def call_ollama(prompt, max_tokens=512, temperature=0.0, timeout=120):
    """
    Call Ollama, handle streaming NDJSON and return a dict with the combined text.
    Raises RuntimeError on HTTP errors.
    """
    url = f"{OLLAMA_HOST}/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    try:
        with requests.post(url, json=payload, timeout=timeout, stream=True) as resp:
            if not resp.ok:
                body = resp.text[:4096] if resp.text else "<no body>"
                raise RuntimeError(f"Ollama HTTP {resp.status_code}: {body}")

            content_type = resp.headers.get("Content-Type", "")
            # streaming NDJSON
            if "ndjson" in content_type or "application/x-ndjson" in content_type or resp.encoding is None:
                parts = []
                for raw in resp.iter_lines(decode_unicode=True):
                    if not raw:
                        continue
                    try:
                        obj = json.loads(raw)
                        chunk = obj.get("response")
                        if isinstance(chunk, str):
                            parts.append(chunk)
                    except Exception:
                        # include raw for debugging
                        parts.append(raw)
                combined = "".join(parts)
                return {"model": OLLAMA_MODEL, "text": combined}
            else:
                # Non-streaming JSON
                return resp.json()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Ollama request failed: {e}") from e

def call_flowise(flow_id, input_data, timeout=120):
    if not flow_id:
        raise ValueError("flow_id required for call_flowise")
    payload = {"flow_id": flow_id, "input": input_data}
    resp = requests.post(FLOWISE_RUN_URL, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()

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
    """
    Run the agent workflow for agent_id and write logs/state/output under PERSISTENT_DIR/agents/<id>.
    Intended to be called from server.py (background thread) or by an RQ worker.
    """
    agent_dir = PERSISTENT_DIR / "agents" / agent_id
    try:
        append_agent_log(agent_dir, f"[{time.asctime()}] Agent started")
        write_agent_state(agent_dir, {"status": "running", "progress": 0})

        input_path = agent_dir / "input.json"
        if not input_path.exists():
            raise RuntimeError("input.json missing for agent " + agent_id)
        payload = json.loads(input_path.read_text())

        flow_id = payload.get("flow_id")
        flow_out = None
        if flow_id:
            append_agent_log(agent_dir, f"[{time.asctime()}] Calling Flowise flow {flow_id}")
            try:
                flow_out = call_flowise(flow_id, payload.get("context", {}))
                append_agent_log(agent_dir, f"[{time.asctime()}] Flowise responded")
            except Exception as e:
                append_agent_log(agent_dir, f"[{time.asctime()}] Flowise failed: {e}")
                flow_out = {"error": str(e)}

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
        try:
            write_agent_state(agent_dir, {"status": "failed", "progress": 0, "error": str(e)})
        except Exception:
            pass
        append_agent_log(agent_dir, f"[{time.asctime()}] Agent failed: {e}")
        raise