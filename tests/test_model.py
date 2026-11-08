import json

import httpx
import pytest

from pharos.model import BharatCodeBackend, ModelError, run_agent
from pharos.safety import sandbox_policy
from pharos.tools import ToolBox

# Shape copied from a real BharatCode response.
API_REPLY = {
    "id": "chatcmpl-bc-1",
    "object": "chat.completion",
    "model": "qwen-3.8-27b",
    "choices": [{
        "index": 0,
        "finish_reason": "stop",
        "message": {
            "role": "assistant",
            "content": "\n\npong",
            "refusal": None,
            "reasoning_content": "thinking...",
        },
    }],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}


def make_backend(handler, **kw) -> BharatCodeBackend:
    return BharatCodeBackend(
        api_key="test-key", base_url="https://example.test/v1",
        transport=httpx.MockTransport(handler), **kw,
    )


def test_chat_parses_reply_and_drops_reasoning():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=API_REPLY)

    msg = make_backend(handler).chat([{"role": "user", "content": "ping"}])
    assert msg == {"role": "assistant", "content": "pong"}
    assert seen["url"] == "https://example.test/v1/chat/completions"
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["model"] == "qwen-3.8-27b"


def test_secrets_are_redacted_before_sending():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return httpx.Response(200, json=API_REPLY)

    make_backend(handler).chat([{"role": "user", "content": "db_password=hunter2 and more"}])
    assert "hunter2" not in seen["body"]
    assert "[REDACTED]" in seen["body"]


def test_dry_run_sends_nothing_and_shows_payload():
    def handler(request):  # pragma: no cover
        raise AssertionError("network must not be used in dry-run")

    msg = make_backend(handler, dry_run=True).chat([{"role": "user", "content": "token=abc123"}])
    assert "Dry run" in msg["content"]
    assert "abc123" not in msg["content"]


def test_missing_key_gives_clear_error(monkeypatch):
    monkeypatch.delenv("BHARATCODE_API_KEY", raising=False)
    with pytest.raises(ModelError, match="BHARATCODE_API_KEY"):
        BharatCodeBackend(api_key="").chat([{"role": "user", "content": "hi"}])


def test_client_errors_are_not_retried_and_hide_nothing_secret():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401, text="bad key")

    with pytest.raises(ModelError, match="401"):
        make_backend(handler).chat([{"role": "user", "content": "hi"}])
    assert len(calls) == 1


class FakeBackend:
    """Scripted replies; records what it was sent."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []

    def chat(self, messages, tools=None):
        self.sent.append([dict(m) for m in messages])
        return self.replies.pop(0)


def tool_call(name, args, id_="c1"):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": id_, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
    ]}


def test_agent_loop_runs_tool_then_returns_final_answer(tmp_path):
    (tmp_path / "a.conf").write_text("Port 22\n")
    fake = FakeBackend([
        tool_call("read_file", {"path": "a.conf"}),
        {"role": "assistant", "content": "Port is 22."},
    ])
    steps = []
    out = run_agent(fake, ToolBox(sandbox_policy(tmp_path)), "sys", "user",
                    on_tool=lambda n, a: steps.append(n))
    assert out == "Port is 22."
    assert steps == ["read_file"]
    tool_msg = fake.sent[1][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "c1"
    assert "Port 22" in tool_msg["content"]


def test_agent_loop_survives_bad_tool_arguments(tmp_path):
    bad = {"role": "assistant", "content": "", "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": "{not json"}}
    ]}
    fake = FakeBackend([bad, {"role": "assistant", "content": "ok"}])
    assert run_agent(fake, ToolBox(sandbox_policy(tmp_path)), "s", "u") == "ok"
    assert "not valid JSON" in fake.sent[1][-1]["content"]


def test_agent_loop_stops_after_max_steps(tmp_path):
    (tmp_path / "a").write_text("x")
    fake = FakeBackend([tool_call("list_dir", {"path": "."}) for _ in range(3)])
    out = run_agent(fake, ToolBox(sandbox_policy(tmp_path)), "s", "u", max_steps=3)
    assert "too many steps" in out
