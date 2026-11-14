"""OpenRouter chat-completions client: image as base64 data URL, retry on 429/5xx/timeouts with backoff.

Records per call: model, finish_reason (must be "stop"), full message content, usage (incl. cost), errors.
The API key is read from OPENROUTER_API_KEY (or a .env file at the repo root) and is never logged.
"""
from __future__ import annotations

import base64
import os
import random
import time
from pathlib import Path

import requests

API_URL = "https://openrouter.ai/api/v1/chat/completions"
REPO_ROOT = Path(__file__).resolve().parent.parent
MAX_TRIES = 6
TIMEOUT_S = 900  # long reasoning replies can take many minutes
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524, 529}


def load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    """Minimal .env loader: KEY=VALUE lines; variables already in the environment win. Prints nothing."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        v = v.strip().strip('"').strip("'")
        if k and v and not os.environ.get(k):
            os.environ[k] = v


def api_key() -> str:
    load_dotenv()
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set (export it or put it in .env at the repo root)")
    return key


def image_data_url(png_path: str | Path) -> str:
    data = base64.standard_b64encode(Path(png_path).read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def build_body(model: str, prompt: str, png_path: str | Path, *, max_tokens: int, effort: str) -> dict:
    return {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_data_url(png_path)}},
            ],
        }],
        "temperature": 0,  # sent, but not listed as supported for either model on OpenRouter: may be ignored
        "max_tokens": max_tokens,
        "reasoning": {"effort": effort},
        "usage": {"include": True},
    }


def _content_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # some providers return content parts
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content)


def call(model: str, prompt: str, png_path: str, *, max_tokens: int = 32000, effort: str = "high") -> dict:
    """One model call. Never raises for API problems: returns a dict with `error` set instead.

    Keys: model, content, finish_reason, native_finish_reason, usage, cost, raw, error, attempts, latency_s, retry_log.
    """
    out = {"model": model, "content": "", "finish_reason": None, "native_finish_reason": None, "usage": None,
           "cost": None, "raw": None, "error": None, "attempts": 0, "latency_s": None, "retry_log": []}
    try:
        headers = {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json",
                   "X-Title": "visual-task-factory-eval"}
        body = build_body(model, prompt, png_path, max_tokens=max_tokens, effort=effort)
    except Exception as e:  # missing key / unreadable image (message never contains the key)
        out["error"] = f"setup: {e}"
        return out

    t0 = time.time()
    for attempt in range(1, MAX_TRIES + 1):
        out["attempts"] = attempt
        retry_reason = None
        try:
            r = requests.post(API_URL, headers=headers, json=body, timeout=TIMEOUT_S)
            if r.status_code in RETRY_STATUS:
                retry_reason = f"HTTP {r.status_code}: {r.text[:300]}"
            elif r.status_code != 200:
                out["error"] = f"HTTP {r.status_code}: {r.text[:1000]}"
                break
            else:
                data = r.json()
                out["raw"] = data
                err = data.get("error")
                choice = (data.get("choices") or [{}])[0]
                if err:  # OpenRouter can return 200 with an error object (e.g. upstream failure)
                    code = err.get("code") if isinstance(err, dict) else None
                    retry_reason = f"API error {code}: {str(err)[:300]}"
                    if isinstance(code, int) and code not in RETRY_STATUS:
                        out["error"] = retry_reason
                        break
                elif choice.get("error"):
                    retry_reason = f"choice error: {str(choice['error'])[:300]}"
                elif not choice:
                    retry_reason = "no choices in response"
                else:
                    msg = choice.get("message") or {}
                    out["content"] = _content_text(msg.get("content"))
                    out["finish_reason"] = choice.get("finish_reason")
                    out["native_finish_reason"] = choice.get("native_finish_reason")
                    out["usage"] = data.get("usage")
                    out["cost"] = (data.get("usage") or {}).get("cost")
                    out["error"] = None
                    break
        except (requests.Timeout, requests.ConnectionError) as e:
            retry_reason = f"{type(e).__name__}: {str(e)[:200]}"
        except ValueError as e:  # body was not JSON
            retry_reason = f"bad JSON: {str(e)[:200]}"

        out["retry_log"].append({"attempt": attempt, "reason": retry_reason})
        out["error"] = retry_reason
        if attempt < MAX_TRIES:
            time.sleep(min(60.0, 2 ** attempt) + random.uniform(0, 1))
    out["latency_s"] = round(time.time() - t0, 2)
    return out
