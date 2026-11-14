"""Pull the answer out of a model reply (the `parsed` column).

Only the last `FINAL ANSWER:` line counts. Returns None when no answer can be read; that scores as wrong, not as an
API error.
"""
from __future__ import annotations

import json
import re

_FINAL = re.compile(r"final\s+answer\s*[:：]?[ \t]*(.*)", re.IGNORECASE)
_NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_CHOICE = re.compile(r"^(?:option\s+|choice\s+)?[(\[]?([A-Za-z])[)\]]?(?=$|[\s.:,)\-])", re.IGNORECASE)
_SEQ_SPLIT = re.compile(r"\s*(?:,|;|->|→|⇒|\|)\s*")


def _final_line(response: str) -> str | None:
    lines = response.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        m = _FINAL.search(lines[i])
        if not m:
            continue
        text = m.group(1).strip()
        if not text:  # "FINAL ANSWER:" alone, answer on the next non-empty line
            text = next((ln.strip() for ln in lines[i + 1:] if ln.strip()), "")
        return text or None
    return None


def _clean(text: str) -> str:
    text = re.sub(r"\\boxed\s*\{(.*)\}", r"\1", text)
    text = re.sub(r"\\text\s*\{([^}]*)\}", r"\1", text)
    text = text.replace("**", "").replace("__", "").replace("`", "").replace("$", "")
    text = text.strip().strip("\"'“”‘’").strip()
    return text.rstrip(".").strip()


def _number(text: str):
    text = text.replace("−", "-").replace("–", "-")
    text = re.sub(r"(?<=\d)[,\u00a0\u202f ](?=\d{3}\b)", "", text)  # thousands separators
    m = _NUMBER.search(text)
    return float(m.group(0)) if m else None


def extract(response: str, answer_type: str):
    if not response:
        return None
    raw = _final_line(response)
    if raw is None:
        return None
    text = _clean(raw)
    if not text:
        return None

    if answer_type in ("number", "integer"):
        x = _number(text)
        if x is None:
            return None
        if answer_type == "integer" and x.is_integer():
            return int(x)
        return x
    if answer_type == "multiple_choice":
        m = _CHOICE.match(text)
        return m.group(1).upper() if m else None
    if answer_type == "sequence":
        if text.startswith("["):
            try:
                items = json.loads(text)
                if isinstance(items, list):
                    return [str(x).strip() for x in items if str(x).strip()]
            except json.JSONDecodeError:
                pass
        text = text.strip("[]()")
        items = [_clean(x) for x in _SEQ_SPLIT.split(text)]
        items = [x for x in items if x]
        return items or None
    if answer_type == "label":
        return text
    raise ValueError(f"unknown answer_type {answer_type!r}")
