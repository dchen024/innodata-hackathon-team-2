"""Shared fixtures for the factory test suite (generator / validator / render / submission format).

Everything expensive is built ONCE per session into a pytest temp dir:
    built_set   configs/final.json rebuilt from seeds and validated (12 tasks, ~8 s)
    generated   ~20 freshly generated + rendered tasks across question types and levels 2-3 (~12 s)

No test may reach the network: .env holds real OpenRouter / Anthropic keys. The autouse `no_network` fixture
blocks sockets, requests and the Anthropic client, and hides the keys, for every test in this folder.
"""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
QTYPES = ["min_stops", "reroute_lines", "transfer_station", "count_stops", "accessible_route"]


class NetworkBlocked(RuntimeError):
    pass


def _blocked(*a, **k):
    raise NetworkBlocked("network access is disabled in tests (no paid API calls)")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    import requests
    monkeypatch.setattr(requests, "post", _blocked)
    monkeypatch.setattr(requests, "get", _blocked)
    monkeypatch.setattr(requests.Session, "request", _blocked)
    try:
        import anthropic
        monkeypatch.setattr(anthropic, "Anthropic", _blocked)
    except ImportError:
        pass
    import eval.openrouter as orr
    monkeypatch.setattr(orr, "load_dotenv", lambda *a, **k: None)
    for k in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    yield


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


@pytest.fixture(scope="session")
def built_set(tmp_path_factory):
    """configs/final.json built from seeds and validated, exactly as `python -m factory build` does."""
    from generator.build import build_set
    from validate.run import validate_set
    out = tmp_path_factory.mktemp("candidates")
    build_set(str(ROOT / "configs" / "final.json"), str(out))
    raw = {r["task_id"]: r for r in read_jsonl(out / "tasks.jsonl")}      # before validate_set adds checks
    report = validate_set(str(out))
    return dict(dir=out, report=report, records=read_jsonl(out / "tasks.jsonl"), raw=raw)


@pytest.fixture(scope="session")
def generated(tmp_path_factory):
    """Fresh tasks (not in any committed spec): {qtype: [(seed, level, data, question, png)]}.
    data carries layout + question exactly like generator/build.py writes it."""
    from generator.families import get_family
    fam = get_family("subway")
    out = tmp_path_factory.mktemp("generated")
    tasks = []
    for i in range(45):
        qt, level, seed = QTYPES[i % 5], 2 + (i // 5) % 2, 7100 + i
        try:
            data, q = fam.generate(seed, level, qt, "clean")
        except RuntimeError:                       # generator gave up after 400 attempts; not under test here
            continue
        png = out / f"{seed}.png"
        data["layout"] = fam.render(data, str(png))
        data["question"] = dict(question_type=q.question_type, question=q.question, answer=q.answer,
                                answer_type=q.answer_type, meta=q.meta)
        data = json.loads(json.dumps(data, default=str))      # same round trip as data/<id>.json
        tasks.append(dict(seed=seed, level=level, qtype=qt, data=data, q=q, png=str(png)))
    return tasks
