"""Smoke-test the BharatCode API before building on it.

Checks, in order:
  1. a plain chat call works
  2. the model returns a tool call when given a tool definition
Never prints the API key.

Env vars (put them in .env, which must be in .gitignore):
  BHARATCODE_BASE_URL   e.g. the base URL shown on the API tab (no trailing slash)
  BHARATCODE_API_KEY
  BHARATCODE_MODEL      e.g. qwen-3.8-27b (check the API tab)

Usage:
  uv run --env-file .env python scripts/api_check.py
  uv run --env-file .env python scripts/api_check.py --path /responses   # if the API is Responses-style
"""
import argparse
import json
import os
import sys
import time

import httpx

TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a text file and return its contents.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
}


def need(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        sys.exit(f"Missing env var {name}. Set it in .env and run with: uv run --env-file .env ...")
    return val


def post(client: httpx.Client, url: str, key: str, body: dict) -> tuple[int, dict | str, float]:
    t0 = time.time()
    r = client.post(url, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=60)
    dt = time.time() - t0
    try:
        return r.status_code, r.json(), dt
    except Exception:
        return r.status_code, r.text[:500], dt


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="/chat/completions", help="endpoint path after the base URL")
    args = ap.parse_args()

    base = need("BHARATCODE_BASE_URL").rstrip("/")
    key = need("BHARATCODE_API_KEY")
    model = need("BHARATCODE_MODEL")
    url = base + args.path
    print(f"POST {url}  model={model}\n")

    with httpx.Client() as c:
        # 1. plain call
        body = {"model": model, "messages": [{"role": "user", "content": "Reply with exactly one word: pong"}]}
        status, data, dt = post(c, url, key, body)
        print(f"[1] plain chat: HTTP {status} in {dt:.1f}s")
        print(json.dumps(data, indent=2)[:1200] if isinstance(data, dict) else data)
        if status != 200:
            sys.exit("\nPlain call failed. Check the base URL, key, model name and endpoint path on the API tab.")

        # 2. tool call
        body = {
            "model": model,
            "messages": [{"role": "user", "content": "Use the read_file tool to read /etc/hostname."}],
            "tools": [TOOL],
        }
        status, data, dt = post(c, url, key, body)
        print(f"\n[2] tool call: HTTP {status} in {dt:.1f}s")
        if isinstance(data, dict):
            try:
                msg = data["choices"][0]["message"]
                calls = msg.get("tool_calls")
                print("tool_calls:", json.dumps(calls, indent=2) if calls else "NONE")
                print("\nRESULT:", "tool calling works" if calls else "no tool call returned: use the JSON-in-text fallback")
            except Exception:
                print(json.dumps(data, indent=2)[:1200])
                print("\nUnexpected shape (maybe Responses-style?). Paste this output back to me.")
        else:
            print(data)


if __name__ == "__main__":
    main()
