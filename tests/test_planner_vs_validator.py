"""The core "verifiable answer" claim: the generator's Dijkstra planner and the validator's independent search
(0-1 BFS / leg enumeration / chips read from the rendered layout) agree on fresh seeds."""
from __future__ import annotations

from collections import Counter

import pytest

from generator.families.subway.family import accessible_set, plan
from validate.families.subway import check, graph


def test_enough_fresh_tasks_across_types(generated):
    c = Counter(t["qtype"] for t in generated)
    assert len(generated) >= 15 and len(c) >= 4, c   # accessible_route is rarer under the v0.3 rules


def test_validator_recomputes_every_answer(generated):
    bad = []
    for t in generated:
        res = check(dict(answer=t["q"].answer, question=t["q"].question), t["data"], t["png"])
        if not res["answer_recomputed"]["passed"]:
            bad.append((t["seed"], t["qtype"], t["q"].answer, res["answer_recomputed"]))
    assert not bad


def test_render_matches_network_and_memory_trap(generated):
    """Chips drawn == services stopping under the service change; level>=2 answers differ from normal service."""
    bad = []
    for t in generated:
        res = check(dict(answer=t["q"].answer, question=t["q"].question), t["data"], t["png"])
        for k in ("render_matches_data", "memory_trap", "unique_answer", "chip_legibility"):
            if res.get(k, {}).get("passed") is False:
                bad.append((t["seed"], t["qtype"], k, res[k]))
    assert not bad


def test_question_names_origin_and_dest_as_printed(generated):
    for t in generated:
        labels = t["data"]["layout"]["labels"]
        m = t["q"].meta
        for s in (m["origin"], m["dest"]):
            assert s in labels and labels[s]["text"] in t["q"].question


def test_answer_types(generated):
    want = dict(min_stops="integer", count_stops="integer", transfer_station="label",
                reroute_lines="sequence", accessible_route="sequence")
    for t in generated:
        q = t["q"]
        assert q.answer_type == want[t["qtype"]]
        if q.answer_type == "integer":
            assert isinstance(q.answer, int) and not isinstance(q.answer, bool) and q.answer > 0
        elif q.answer_type == "sequence":
            assert isinstance(q.answer, list) and q.answer and all(isinstance(x, str) for x in q.answer)
        else:
            assert isinstance(q.answer, str) and q.answer


def test_accessible_set_matches_printed_symbols(generated):
    """The planner's wheelchair set and the validator's (read from label symbols) are the same stations."""
    g = graph()
    for t in [t for t in generated if t["qtype"] == "accessible_route"]:
        iv = set(t["data"]["stations_in_view"])
        printed = {s for s, v in t["data"]["layout"]["labels"].items() if v.get("accessible")}
        assert accessible_set(g, iv) & set(t["data"]["layout"]["labels"]) == printed


def test_accessible_route_answer_differs_from_normal_service(generated, built_set):
    g = graph()
    cases = [(t["data"], t["q"].answer) for t in generated if t["qtype"] == "accessible_route" and t["level"] >= 2]
    import json
    for r in built_set["records"]:
        if r["question_type"] == "accessible_route" and r["level"] >= 2:
            cases.append((json.loads((built_set["dir"] / r["data"]).read_text()), r["answer"]))
    assert cases
    same = []
    for data, ans in cases:
        iv = set(data["stations_in_view"])
        m = data["question"]["meta"]
        _, trips0 = plan(g, iv, None, m["origin"], m["dest"], access=accessible_set(g, iv))
        normal = {tuple(g["routes"][l[0]]["name"] for l in tr) for tr in trips0}
        if tuple(ans) in normal:
            same.append((data["seed"], ans))
    assert not same, f"weekend accessible answer equals the normal-service one: {same}"
