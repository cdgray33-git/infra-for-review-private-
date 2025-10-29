# Minimal Ollama -> LangChain LLM adapter.
# Implements langchain.llms.base.LLM so it satisfies LLMChain / Runnable expectations.
import requests
from typing import Optional, List, Mapping, Any
from langchain.llms.base import LLM

class OllamaLLM(LLM):
    """
    Minimal adapter for an Ollama HTTP server.
    Configure with ollama_host (e.g. http://ollama:11434) and model name.
    """

    ollama_host: str = "http://ollama:11434"
    model: str = "llama3"

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, ollama_host: str = None, model: str = None, **kwargs):
        if ollama_host:
            self.ollama_host = ollama_host
        if model:
            self.model = model
        super().__init__(**kwargs)

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        """
        Synchronous call to Ollama. Adjust JSON body according to your Ollama API.
        """
        url = self.ollama_host.rstrip("/") + "/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
        }
        try:
            resp = requests.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                return data.get("text") or data.get("output") or data.get("result") or str(data)
            return str(data)
        except Exception as e:
            raise RuntimeError(f"OllamaLLM request failed: {e}")

    async def _acall(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._call, prompt, stop)

    def _identifying_params(self) -> Mapping[str, Any]:
        return {"model": self.model, "host": self.ollama_host}

    @property
    def _llm_type(self) -> str:
        return "ollama"