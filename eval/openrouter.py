"""OpenRouter chat-completions client: image as base64 data URL, retry on 429/5xx/timeouts with backoff.

Must record per call: model, finish_reason (must be "stop"), full message content, usage (incl. cost), errors.
"""
API_URL = "https://openrouter.ai/api/v1/chat/completions"


def call(model: str, prompt: str, png_path: str, *, max_tokens: int, effort: str = "high") -> dict:
    raise NotImplementedError("TODO")
