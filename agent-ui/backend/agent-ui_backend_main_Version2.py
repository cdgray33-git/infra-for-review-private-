# (patched file - startup_event made resilient)
"""
Full LangChain Agent backend (FastAPI) with WebSocket streaming.
- Initializes LangChain agent with Tools for Mail Assistant, DCO, and Server Team.
- Exposes:
  - POST /chat   -> synchronous call (returns final response)
  - WS  /ws/chat -> streaming interaction (handshake requires api_key)
Notes:
- This is an MVP. Harden auth, CORS, and RBAC for production.
"""
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
from langchain.callbacks.manager import CallbackManager
from ollama_llm import OllamaLLM
import logging

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
    allow_origins=["*"],  # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# thread pool for blocking agent runs
executor = ThreadPoolExecutor(max_workers=4)

# --- Tools / wrappers ---
def call_mail_assistant_run(args: Dict[str, Any]) -> Dict[str, Any]:
    payload = args if isinstance(args, dict) else {"agent_id": args}
    url = f"{MAIL_ASSISTANT_URL.rstrip('/')}/run"
    resp = requests.post(url, json=payload, timeout=20)
    resp.raise_for_status()
    return resp.json()

def fetch_mail_output(args: Dict[str, Any]) -> Dict[str, Any]:
    agent_id = args.get("agent_id") if isinstance(args, dict) else args
    path = os.path.join(PERSISTENT_DIR, "agents", agent_id, "output.json")
    if os.path.exists(path):
        return json.load(open(path))
    return {"error": "no output found", "agent_id": agent_id}

def dco_health(_: Dict[str, Any] = None) -> Dict[str, Any]:
    resp = requests.get(f"{DCO_AGENT_URL.rstrip('/')}/health", timeout=5)
    resp.raise_for_status()
    return resp.json()

def server_team_action(args: Dict[str, Any]) -> Dict[str, Any]:
    server_url = os.environ.get("SERVER_TEAM_URL")
    if not server_url:
        return {"error": "SERVER_TEAM_URL not configured"}
    resp = requests.post(server_url.rstrip('/') + "/action", json=args, timeout=30)
    resp.raise_for_status()
    return resp.json()

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
]

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

@app.on_event("startup")
async def startup_event():
    """
    Try to build the agent at startup, but do not crash the process if initialization fails.
    The actual agent will be created lazily on first request if AGENT is None.
    """
    global AGENT
    try:
        AGENT = build_agent()
        logging.getLogger("agent_ui_startup").info("Agent initialized at startup.")
    except Exception as e:
        logging.getLogger("agent_ui_startup").warning("Agent build at startup failed (will initialize lazily): %s", e)
        AGENT = None

@app.get("/")
async def index():
    frontend_html = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    if os.path.exists(frontend_html):
        return HTMLResponse(open(frontend_html, "r").read())
    return {"status": "agent-ui up"}

@app.post("/chat")
async def chat(request: Request):
    payload = await request.json()
    user_input = payload.get("input") or payload.get("text") or ""
    if not user_input:
        raise HTTPException(status_code=400, detail="missing input")
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

# WebSocket endpoint and remaining code unchanged (omitted here for brevity).
