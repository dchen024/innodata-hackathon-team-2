"""OpenRouter chat-completions client: image as base64 data URL, retry on 429/5xx/timeouts with backoff.

Must record per call: model, finish_reason (must be "stop"), full message content, usage (incl. cost), errors.
"""
from __future__ import annotations

import base64
import os
import random
import time
from pathlib import Path

import requests

API_URL = "https://openrouter.ai/api/v1/chat/completions"
TEMPERATURE = 0
MAX_ATTEMPTS = 6
TIMEOUT = (30, 900)  # connect, read (high-effort reasoning can take minutes)
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524, 529}


def api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        env = Path(__file__).resolve().parent.parent / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.strip().startswith("OPENROUTER_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip("\"'")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set (environment or .env)")
    return key


def build_payload(model: str, prompt: str, png_path: str, *, max_tokens: int, effort: str) -> dict:
    image = base64.b64encode(Path(png_path).read_bytes()).decode("ascii")
    return {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image}"}},
            ],
        }],
        "temperature": TEMPERATURE,
        "max_tokens": max_tokens,
        "reasoning": {"effort": effort},
        "usage": {"include": True},
    }


def _backoff(attempt: int, retry_after: str | None) -> float:
    if retry_after:
        try:
            return min(120.0, float(retry_after))
        except ValueError:
            pass
    return min(60.0, 2.0 ** attempt) + random.uniform(0, 1)


def _content_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, list):  # some providers return content parts
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return (content or "").strip()


def call(model: str, prompt: str, png_path: str, *, max_tokens: int, effort: str = "high") -> dict:
    """One model call. `error` is "" (usable reply), "length" (cut off) or "api_error" (no usable reply)."""
    payload = build_payload(model, prompt, png_path, max_tokens=max_tokens, effort=effort)
    headers = {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json",
               "X-Title": "transport-visual-task-factory"}
    result = {"model": model, "finish_reason": "", "native_finish_reason": "", "content": "", "reasoning": "",
              "usage": {}, "cost": 0.0, "error": "api_error", "attempts": 0, "attempt_errors": [], "response": None}

    for attempt in range(1, MAX_ATTEMPTS + 1):
        result["attempts"] = attempt
        retry_after = None
        try:
            r = requests.post(API_URL, json=payload, headers=headers, timeout=TIMEOUT)
            retry_after = r.headers.get("Retry-After")
            try:
                body = r.json()
            except ValueError:
                body = None
            if r.status_code != 200 or not isinstance(body, dict):
                msg = f"HTTP {r.status_code}: {r.text[:500]}"
                result["attempt_errors"].append(msg)
                if r.status_code in RETRY_STATUS or (r.status_code == 200 and body is None):
                    raise _Retry
                return result  # 400/401/402/403/404: retrying will not help
            result["response"] = body
            if body.get("error") or not body.get("choices"):
                result["attempt_errors"].append(f"error in body: {str(body.get('error') or body)[:500]}")
                raise _Retry
            choice = body["choices"][0]
            message = choice.get("message") or {}
            result.update(
                finish_reason=choice.get("finish_reason") or "",
                native_finish_reason=choice.get("native_finish_reason") or "",
                content=_content_text(message),
                reasoning=message.get("reasoning") or "",
                usage=body.get("usage") or {},
            )
            result["cost"] += float(result["usage"].get("cost") or 0.0)  # summed over retried attempts
            if result["finish_reason"] == "length":
                result["error"] = "length"
                return result
            if choice.get("error") or not result["content"]:
                result["attempt_errors"].append(
                    f"no usable content (finish_reason={result['finish_reason']!r}, error={choice.get('error')})")
                raise _Retry
            result["error"] = ""
            return result
        except _Retry:
            pass
        except requests.RequestException as e:
            result["attempt_errors"].append(f"{type(e).__name__}: {e}")
        if attempt < MAX_ATTEMPTS:
            time.sleep(_backoff(attempt, retry_after))
    result["error"] = "api_error"
    return result


class _Retry(Exception):
    pass
