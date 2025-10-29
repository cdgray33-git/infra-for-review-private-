# Simple Ollama -> LangChain LLM adapter.
# Implements langchain.llms.base.LLM so it satisfies LLMChain / Runnable expectations.
import requests
from typing import Optional, List, Mapping, Any
from langchain.llms.base import LLM
from pydantic import BaseModel

class OllamaLLM(LLM):
    """
    Minimal adapter for an Ollama HTTP server.
    Configure with ollama_host (e.g. http://ollama:11434) and model name.
    """

    ollama_host: str = "http://ollama:11434"
    model: str = "llama3"

    class Config:
        arbitrary_types_allowed = True

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        """
        Synchronous call. Adjust JSON body if your Ollama API differs.
        """
        url = self.ollama_host.rstrip("/") + "/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            # adjust other options here (temperature, max_tokens) if your API supports them
        }
        try:
            resp = requests.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            # Try to extract a reasonable text field - adjust based on your Ollama server response.
            if isinstance(data, dict):
                # common keys: "text", "output", "result"
                return data.get("text") or data.get("output") or data.get("result") or str(data)
            return str(data)
        except Exception as e:
            # Raise a clear runtime error so calling code can log it and fallback as needed.
            raise RuntimeError(f"OllamaLLM request failed: {e}")

    async def _acall(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        # Run synchronous code in thread pool if you don't have an async HTTP client
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._call, prompt, stop)

    def _identifying_params(self) -> Mapping[str, Any]:
        return {"model": self.model, "host": self.ollama_host}

    @property
    def _llm_type(self) -> str:
        return "ollama"