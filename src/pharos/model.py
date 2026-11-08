"""Model backend: BharatCode's OpenAI-compatible chat API, plus the tool loop.

The backend is a tiny interface (`chat`), so a local model can be swapped in later.
"""
from __future__ import annotations

import json
import os
import time
from typing import Callable

import httpx

from .safety import redact
from .tools import ToolBox

DEFAULT_BASE_URL = "https://bharatcode.ai/api/model/v1"
DEFAULT_MODEL = "qwen-3.8-27b"


class ModelError(Exception):
    pass


class BharatCodeBackend:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        dry_run: bool = False,
        timeout: float = 90.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.api_key = api_key or os.environ.get("BHARATCODE_API_KEY", "")
        self.base_url = (base_url or os.environ.get("BHARATCODE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or os.environ.get("BHARATCODE_MODEL") or DEFAULT_MODEL
        self.dry_run = dry_run
        self.timeout = timeout
        self._transport = transport

    @staticmethod
    def _clean(messages: list[dict]) -> list[dict]:
        """Redact secrets from everything leaving the machine (defence in depth)."""
        out = []
        for m in messages:
            m = dict(m)
            if isinstance(m.get("content"), str):
                m["content"], _ = redact(m["content"])
            out.append(m)
        return out

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        body: dict = {"model": self.model, "messages": self._clean(messages)}
        if tools:
            body["tools"] = tools

        if self.dry_run:
            shown = json.dumps(body, indent=2, ensure_ascii=False)
            return {
                "role": "assistant",
                "content": "**Dry run: nothing was sent.** This is exactly what would be sent:\n\n"
                           f"```json\n{shown}\n```",
            }
        if not self.api_key:
            raise ModelError("Set BHARATCODE_API_KEY (get a key from the API tab on bharatcode.ai).")

        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        last = "unknown error"
        for attempt in range(2):
            try:
                with httpx.Client(timeout=self.timeout, transport=self._transport) as c:
                    r = c.post(url, headers=headers, json=body)
            except httpx.TransportError as e:
                last = f"network error: {e.__class__.__name__}"
            else:
                if r.status_code == 200:
                    return self._parse(r)
                last = f"HTTP {r.status_code}: {r.text[:300]}"
                if r.status_code < 500 and r.status_code != 429:
                    break
            if attempt == 0:
                time.sleep(2)
        raise ModelError(f"BharatCode API call failed ({last})")

    @staticmethod
    def _parse(r: httpx.Response) -> dict:
        try:
            msg = r.json()["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise ModelError(f"Unexpected API response: {r.text[:300]}")
        out = {"role": "assistant", "content": (msg.get("content") or "").strip()}
        if msg.get("tool_calls"):
            out["tool_calls"] = msg["tool_calls"]
        return out  # reasoning_content is dropped on purpose


def run_agent(
    backend: BharatCodeBackend,
    toolbox: ToolBox,
    system: str,
    user: str,
    max_steps: int = 8,
    on_tool: Callable[[str, dict], None] | None = None,
) -> str:
    """Let the model call tools until it answers. Returns the final text."""
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    for _ in range(max_steps):
        msg = backend.chat(messages, toolbox.schemas())
        calls = msg.get("tool_calls")
        entry = {"role": "assistant", "content": msg.get("content") or ""}
        if calls:
            entry["tool_calls"] = calls
        messages.append(entry)
        if not calls:
            return entry["content"]
        for c in calls:
            name = c.get("function", {}).get("name", "")
            try:
                args = json.loads(c.get("function", {}).get("arguments") or "{}")
            except ValueError:
                args = None
            if on_tool and isinstance(args, dict):
                on_tool(name, args)
            result = toolbox.call(name, args) if args is not None else "error: arguments were not valid JSON"
            messages.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": result})
    return "(Stopped: the model used too many steps. Try a more specific request.)"
