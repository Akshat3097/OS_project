"""Minimal Ollama client (chat + embeddings) using plain HTTP, so it works with any model you pull."""
from __future__ import annotations

import json
from collections.abc import Iterator

import requests

import config


class OllamaClient:
    def __init__(self, url: str = config.OLLAMA_URL, model: str = config.DEFAULT_MODEL, timeout: int = 180):
        self.url = url.rstrip("/")
        self.model = model
        self.timeout = timeout

    # ------------------------------------------------------------------ status
    def available(self) -> bool:
        try:
            return requests.get(f"{self.url}/api/tags", timeout=2).ok
        except requests.RequestException:
            return False

    def list_models(self) -> list[str]:
        try:
            r = requests.get(f"{self.url}/api/tags", timeout=3)
            r.raise_for_status()
            return sorted(m["name"] for m in r.json().get("models", []))
        except (requests.RequestException, ValueError, KeyError):
            return []

    def make_room(self) -> None:
        """Unload any other chat model before using this one. On the 8 GB laptop only one 8B model fits next to the
        desktop, and Ollama 0.40 queues a request for a second model (indefinitely, in our test) instead of unloading
        the idle one. The judge (llama3.1:8b) and the tutor (os-tutor) take turns, so this matters."""
        try:
            loaded = requests.get(f"{self.url}/api/ps", timeout=2).json().get("models", [])
        except (requests.RequestException, ValueError):
            return
        mine = self.model.split(":")[0]
        for m in loaded:
            name = m.get("name", "")
            if name.split(":")[0] != mine and "embed" not in name:
                try:
                    requests.post(f"{self.url}/api/generate", json={"model": name, "keep_alive": 0}, timeout=30)
                except requests.RequestException:
                    pass

    # ------------------------------------------------------------------ chat
    def chat(self, messages: list[dict], options: dict | None = None, fmt: str | dict | None = None) -> str:
        self.make_room()
        body = {"model": self.model, "messages": messages, "stream": False, "keep_alive": config.KEEP_ALIVE,
                "options": {**config.LLM_OPTIONS, **(options or {})}}
        if fmt:
            body["format"] = fmt            # "json" (or a JSON schema) constrains the reply to valid JSON
        r = requests.post(f"{self.url}/api/chat", timeout=self.timeout, json=body)
        r.raise_for_status()
        text = r.json()["message"]["content"]
        return text if fmt else cut_loop(text)

    def chat_stream(self, messages: list[dict], options: dict | None = None) -> Iterator[str]:
        self.make_room()
        sent = ""
        with requests.post(f"{self.url}/api/chat", timeout=self.timeout, stream=True, json={
                "model": self.model, "messages": messages, "stream": True, "keep_alive": config.KEEP_ALIVE,
                "options": {**config.LLM_OPTIONS, **(options or {})}}) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                if "message" in chunk:
                    piece = chunk["message"].get("content", "")
                    if looping(sent + piece):            # the model is repeating itself: stop here
                        break
                    sent += piece
                    yield piece
                if chunk.get("done"):
                    break


def looping(text: str, size: int = 60) -> bool:
    """True when the last `size` characters already appeared twice before: a repetition loop."""
    if len(text) < 4 * size:
        return False
    tail = text[-size:]
    return text.count(tail) >= 3


def cut_loop(text: str, size: int = 60) -> str:
    """Drop everything from the first repeated passage on (a reply that loops is cut where the loop starts)."""
    for end in range(4 * size, len(text) + 1, 20):
        if looping(text[:end], size):
            tail = text[end - size:end]
            first = text.find(tail)
            return text[:first + size].rsplit(". ", 1)[0].rstrip() + "."
    return text

    # ------------------------------------------------------------------ embeddings
    def embed(self, texts: list[str], model: str = config.EMBED_MODEL) -> list[list[float]]:
        r = requests.post(f"{self.url}/api/embed", timeout=self.timeout, json={"model": model, "input": texts})
        if r.status_code == 404 and "model" not in r.text.lower():
            # older Ollama versions only have /api/embeddings (one text per call)
            out = []
            for t in texts:
                r2 = requests.post(f"{self.url}/api/embeddings", timeout=self.timeout,
                                   json={"model": model, "prompt": t})
                r2.raise_for_status()
                out.append(r2.json()["embedding"])
            return out
        r.raise_for_status()
        return r.json()["embeddings"]
