# Minimal, robust Ollama -> LangChain LLM adapter.
# Implements langchain.llms.base.LLM so it satisfies LLMChain / Runnable expectations.
import logging
import requests
from typing import Optional, List, Mapping, Any
from requests.adapters import HTTPAdapter, Retry
from langchain.llms.base import LLM

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

class OllamaLLM(LLM):
    """
    Minimal adapter for an Ollama HTTP server.
    Configure with ollama_host (e.g. "http://ollama:11434") and model name.
    """

    ollama_host: str = "http://ollama:11434"
    model: str = "llama3"
    timeout: int = 30
    retries: int = 1  # simple retry count

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, ollama_host: Optional[str] = None, model: Optional[str] = None, timeout: Optional[int] = None, retries: Optional[int] = None, **kwargs):
        if ollama_host:
            self.ollama_host = ollama_host
        if model:
            self.model = model
        if timeout is not None:
            self.timeout = timeout
        if retries is not None:
            self.retries = retries
        # session with retries
        self._session = requests.Session()
        if self.retries:
            retry_strategy = Retry(
                total=self.retries,
                backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "POST"],
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            self._session.mount("http://", adapter)
            self._session.mount("https://", adapter)
        super().__init__(**kwargs)

    def _parse_response(self, data: Any) -> str:
        """
        Try several common shapes returned by an Ollama-style API.
        Adjust according to your Ollama server's actual response format.
        """
        if data is None:
            return ""
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            # common keys
            for k in ("text", "output", "result", "content"):
                if k in data and data[k]:
                    return data[k]
            # some servers return { "results": [{"content":"..."}] } or similar
            if "results" in data and isinstance(data["results"], list) and data["results"]:
                first = data["results"][0]
                if isinstance(first, dict):
                    for k in ("text", "content", "output", "result"):
                        if k in first and first[k]:
                            return first[k]
                # if result is a primitive
                return str(first)
            # fallback to stringifying
            return str(data)
        # list or other
        try:
            return str(data)
        except Exception:
            return ""

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        """
        Synchronous call to Ollama. Adjust JSON body according to your Ollama API.
        Default endpoint: {ollama_host.rstrip('/')}/api/generate
        """
        url = self.ollama_host.rstrip("/") + "/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
        }
        try:
            resp = self._session.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            parsed = self._parse_response(data)
            logger.debug("Ollama response parsed: %s", parsed[:200])
            return parsed
        except Exception as e:
            logger.exception("OllamaLLM request failed")
            raise RuntimeError(f"OllamaLLM request failed: {e}") from e

    async def _acall(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        # Run sync code in thread pool if async HTTP client not available
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._call, prompt, stop)

    def _identifying_params(self) -> Mapping[str, Any]:
        return {"model": self.model, "host": self.ollama_host}

    @property
    def _llm_type(self) -> str:
        return "ollama"