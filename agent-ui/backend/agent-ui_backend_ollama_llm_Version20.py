"""
Custom Ollama LLM wrapper for LangChain.
This implements a minimal LLM subclass that calls the Ollama /api/generate endpoint,
and returns combined streamed responses (handles Ollama NDJSON streaming).
"""
from typing import Optional, List, Mapping, Any
import os
import requests
import json
from langchain.llms.base import LLM
from pydantic import BaseModel


class OllamaLLM(LLM, BaseModel):
    """
    Minimal Ollama wrapper implementing _call for LangChain LLM compatibility.
    """
    ollama_host: str = os.environ.get("OLLAMA_HOST", "http://ollama:11434")
    model: str = os.environ.get("OLLAMA_MODEL", "llama3")
    timeout: int = 300

    class Config:
        arbitrary_types_allowed = True

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        """Synchronous call returning the aggregated text response."""
        url = f"{self.ollama_host.rstrip('/')}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "max_tokens": 512,
            "temperature": 0.0
        }
        try:
            with requests.post(url, json=payload, stream=True, timeout=self.timeout) as resp:
                resp.raise_for_status()
                parts: List[str] = []
                for raw in resp.iter_lines(decode_unicode=True):
                    if not raw:
                        continue
                    try:
                        obj = json.loads(raw)
                        # Ollama ndjson object usually contains keys like 'response'
                        chunk = None
                        if isinstance(obj, dict):
                            # try keys commonly used
                            for k in ("response", "token", "content"):
                                if k in obj and isinstance(obj[k], str):
                                    chunk = obj[k]
                                    break
                        if chunk:
                            parts.append(chunk)
                        else:
                            # fallback: append raw line
                            parts.append(raw)
                    except Exception:
                        parts.append(raw)
                return "".join(parts)
        except requests.RequestException as e:
            raise RuntimeError(f"Ollama request failed: {e}") from e

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {"model": self.model, "ollama_host": self.ollama_host}

    @property
    def _llm_type(self) -> str:
        return "ollama"