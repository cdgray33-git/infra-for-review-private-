# Lightweight wrapper to expose the FastAPI app object for uvicorn.
# Loads the backend implementation from agent-ui_backend_main_Version2.py at runtime.
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

try:
    app = getattr(module, "app")
except Exception as e:
    raise RuntimeError("Loaded backend module but 'app' was not found") from e
