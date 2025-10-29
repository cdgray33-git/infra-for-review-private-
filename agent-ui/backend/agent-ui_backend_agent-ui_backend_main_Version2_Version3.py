# agent-ui/backend/agent-ui_backend_main_Version2.py
# Patched Agent UI backend that serves the packaged frontend and includes server action tools.
# NOTE: This version imports OllamaLLM from ollama_llm.py (existing file) for compatibility.
import os
import json
import asyncio
from typing import Any, Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
from concurrent.futures import ThreadPoolExecutor
from langchain.agents import initialize_agent, Tool, AgentType

# Import the Ollama wrapper from ollama_llm.py (ensure this file exists in the same folder)
from ollama_llm import OllamaLLM

# server actions helper (you should have created server_actions.py in the same folder)
from server_actions import run_ansible_playbook, restart_compose_service, create_github_issue

# Configuration
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")
MAIL_ASSISTANT_URL = os.environ.get("MAIL_ASSISTANT_URL", "http://mail_assistant:8002")
DCO_AGENT_URL = os.environ.get("DCO_AGENT_URL", "http://dco_agent:8000")
PERSISTENT_DIR = os.environ.get("PERSISTENT_DIR", "/app/persistent")
API_KEY = os.environ.get("AGENT_UI_API_KEY", "changeme")
PORT = int(os.environ.get("AGENT_UI_PORT", "80"))

app = FastAPI(title="Agent UI - LangChain Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten via env/UI_ORIGIN in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# thread pool for blocking agent runs
executor = ThreadPoolExecutor(max_workers=4)


# --- Tools / wrappers ---

def call_mail_assistant_run(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Trigger mail_assistant /run. args expected to contain 'agent_id' or full payload.
    Returns response JSON from mail_assistant.
    """
    payload = args if isinstance(args, dict) else {"agent_id": args}
    url = f"{MAIL_ASSISTANT_URL.rstrip('/')}/run"
    resp = requests.post(url, json=payload, timeout=20)
    resp.raise_for_status()
    return resp.json()


def fetch_mail_output(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Read persistent output.json for an agent (if present).
    args: { "agent_id": "<id>" }
    """
    agent_id = args.get("agent_id") if isinstance(args, dict) else args
    path = os.path.join(PERSISTENT_DIR, "agents", agent_id, "output.json")
    if os.path.exists(path):
        try:
            return json.load(open(path))
        except Exception as e:
            return {"error": "failed to read output.json", "detail": str(e)}
    return {"error": "no output found", "agent_id": agent_id}


def dco_health(_: Dict[str, Any] = None) -> Dict[str, Any]:
    resp = requests.get(f"{DCO_AGENT_URL.rstrip('/')}/health", timeout=5)
    resp.raise_for_status()
    return resp.json()


def server_team_action(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Placeholder: call your server-team endpoint to trigger an action (deploy, restart, etc).
    Example args: {"action":"restart-service","service":"webui"}
    """
    server_url = os.environ.get("SERVER_TEAM_URL")
    if not server_url:
        return {"error": "SERVER_TEAM_URL not configured"}
    resp = requests.post(server_url.rstrip('/') + "/action", json=args, timeout=30)
    resp.raise_for_status()
    return resp.json()


# --- Server action wrappers (new) ---

def server_run_playbook(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    args can be either a string (playbook name) or dict: {"playbook":"site.yml", "extra_vars": {...}}
    """
    if isinstance(args, str):
        playbook = args
        extra = None
    elif isinstance(args, dict):
        playbook = args.get("playbook") or args.get("name")
        extra = args.get("extra_vars")
    else:
        return {"error": "invalid args for server_run_playbook"}
    return run_ansible_playbook(playbook, extra_vars=extra)


def server_restart_service(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    args: { "service": "mail_assistant" } or simple "webui"
    """
    svc = args.get("service") if isinstance(args, dict) else args
    return restart_compose_service(svc, project_dir=os.environ.get("PROJECT_ROOT", "/app"))


def github_create_issue(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    args: { "repo": "owner/repo", "title": "...", "body": "..."}
    """
    repo = args.get("repo") if isinstance(args, dict) else None
    title = args.get("title", "Automated issue")
    body = args.get("body", "")
    token = os.environ.get("GITHUB_TOKEN")
    return create_github_issue(repo, title, body, token)


# Build LangChain Tools
TOOLS = [
    Tool(
        name="mail_run",
        func=lambda args: call_mail_assistant_run(args),
        description="Run the Mail Assistant agent. Provide JSON or {agent_id: '...'}."
    ),
    Tool(
        name="mail_fetch_output",
        func=lambda args: fetch_mail_output(args),
        description="Get the latest output.json for a given agent_id."
    ),
    Tool(
        name="dco_health",
        func=lambda args: dco_health(args),
        description="Return dco agent health status."
    ),
    Tool(
        name="server_action",
        func=lambda args: server_team_action(args),
        description="Call the server team action endpoint with JSON payload."
    ),
    # New server/infrastructure tools:
    Tool(
        name="server_run",
        func=lambda args: server_run_playbook(args),
        description="Run an allowed Ansible playbook on the infrastructure. Provide {playbook:'site.yml', extra_vars:{}} or playbook name."
    ),
    Tool(
        name="server_restart",
        func=lambda args: server_restart_service(args),
        description="Restart a named service in docker-compose (whitelisted). Provide {service: 'webui'} or service name."
    ),
    Tool(
        name="github_create_issue",
        func=lambda args: github_create_issue(args),
        description="Create a GitHub issue in owner/repo. Provide {repo:'owner/repo', title:'', body:''}."
    ),
]


# Initialize Ollama LLM and Agent (initialized lazily to allow env changes before startup)
def build_agent():
    llm = OllamaLLM(ollama_host=OLLAMA_HOST, model=OLLAMA_MODEL)
    agent = initialize_agent(
        tools=TOOLS,
        llm=llm,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        verbose=False,
    )
    return agent

AGENT = None


# --- HTTP endpoints ---


@app.on_event("startup")
async def startup_event():
    global AGENT
    AGENT = build_agent()


@app.get("/")
async def index():
    """
    Try to serve a frontend copy packaged with the backend (preferred):
      ./agent-ui/backend/frontend/index.html
    Fallback to ../frontend/index.html for older layouts.
    """
    candidates = [
        os.path.join(os.path.dirname(__file__), "frontend", "index.html"),
        os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html"),
    ]
    for path in candidates:
        try:
            if os.path.exists(path):
                return HTMLResponse(open(path, "r", encoding="utf-8").read())
        except Exception:
            pass
    return {"status": "agent-ui up"}


@app.post("/chat")
async def chat(request: Request):
    """
    Synchronous POST interface:
    { "input": "Hello", "agent_type": "default" }
    Returns final agent output JSON.
    """
    payload = await request.json()
    user_input = payload.get("input") or payload.get("text") or ""
    if not user_input:
        raise HTTPException(status_code=400, detail="missing input")
    # Simple API key support via header
    api_key = request.headers.get("x-api-key") or request.headers.get("api-key")
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")
    loop = asyncio.get_event_loop()

    def run_agent():
        global AGENT
        if AGENT is None:
            AGENT = build_agent()
        return AGENT.run(user_input)

    result = await loop.run_in_executor(executor, run_agent)
    return {"result": result}


# --- WebSocket streaming endpoint ---


@app.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    """
    WebSocket streaming chat. Protocol:
    1) client sends a JSON handshake: {"api_key":"..."}
    2) then client sends JSON messages: {"input":"...", "context": {...}}.
    The server will respond with events:
      {"type":"info", "payload": "..."}
      {"type":"tool", "payload": {...}}  # tool call returned
      {"type":"result", "payload": "final text"}
      {"type":"error", "payload": "..."}
    We implement thread-safe scheduling so LangChain tool functions can push progress events.
    """
    await ws.accept()
    loop = asyncio.get_event_loop()

    try:
        init_raw = await ws.receive_text()
        init = json.loads(init_raw)
        if init.get("api_key") != API_KEY:
            await ws.send_text(json.dumps({"type":"error","payload":"unauthorized"}))
            await ws.close()
            return

        # helper for other threads to send text on this websocket session
        def send_threadsafe(obj: Dict[str, Any]):
            try:
                loop.call_soon_threadsafe(asyncio.ensure_future, ws.send_text(json.dumps(obj)))
            except Exception:
                # best-effort
                pass

        # create wrapped tools that can notify the websocket of events
        def wrap_tool(fn, tool_name):
            def wrapped(arg):
                send_threadsafe({"type":"info","payload":f"Calling tool {tool_name}..."})
                try:
                    out = fn(arg)
                except Exception as e:
                    send_threadsafe({"type":"error","payload":f"Tool {tool_name} error: {e}"})
                    raise
                send_threadsafe({"type":"tool","payload":{"tool":tool_name,"result":out}})
                return out
            return wrapped

        # Build a per-session agent with wrapped tools so tool calls are reported to WS
        per_session_tools = []
        for t in TOOLS:
            per_session_tools.append(
                Tool(name=t.name, func=wrap_tool(t.func, t.name), description=t.description)
            )

        # lazy agent
        session_llm = OllamaLLM(ollama_host=OLLAMA_HOST, model=OLLAMA_MODEL)
        session_agent = initialize_agent(
            tools=per_session_tools,
            llm=session_llm,
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=False,
        )

        # main loop
        while True:
            msg_raw = await ws.receive_text()
            msg = json.loads(msg_raw)
            user_input = msg.get("input") or msg.get("text") or ""
            if not user_input:
                await ws.send_text(json.dumps({"type":"error","payload":"missing input"}))
                continue

            # run agent in executor so it doesn't block the event loop
            def run_session():
                try:
                    return session_agent.run(user_input)
                except Exception as e:
                    return {"error": str(e)}

            result = await loop.run_in_executor(executor, run_session)
            # send a final result event
            send_threadsafe({"type":"result", "payload": result})
    except WebSocketDisconnect:
        return
    except Exception as e:
        try:
            await ws.send_text(json.dumps({"type":"error","payload": str(e)}))
        except Exception:
            pass
        try:
            await ws.close()
        except Exception:
            pass