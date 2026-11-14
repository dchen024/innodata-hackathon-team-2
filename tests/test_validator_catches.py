"""The validator must reject broken tasks, not just pass good ones (mutation tests on a built task folder)."""
from __future__ import annotations

import json
import shutil

import pytest

from tests.conftest import read_jsonl
from validate.run import validate_set


def one_task(built_set, tmp_path, qtype):
    """Copy of the built folder holding only the first valid task of `qtype`. Returns (dir, record, data)."""
    d = tmp_path / "tasks"
    shutil.copytree(built_set["dir"], d)
    rec = next(r for r in read_jsonl(d / "tasks.jsonl") if r["question_type"] == qtype and r["valid"])
    for k in ("checks", "valid"):
        rec.pop(k)
    data = json.loads((d / rec["data"]).read_text())
    return d, rec, data


def save(d, rec, data):
    (d / "tasks.jsonl").write_text(json.dumps(rec) + "\n")
    (d / rec["data"]).write_text(json.dumps(data))
    return validate_set(str(d))[rec["task_id"]]


def test_built_set_mostly_valid(built_set):
    rep = built_set["report"]
    assert sum(v["valid"] for v in rep.values()) >= 10
    assert all(v["details"]["answer_recomputed"]["passed"] for v in rep.values())
    assert all(r["valid"] == rep[r["task_id"]]["valid"] for r in built_set["records"])


@pytest.mark.parametrize("qtype", ["min_stops", "reroute_lines", "transfer_station"])
def test_wrong_answer_is_caught(built_set, tmp_path, qtype):
    d, rec, data = one_task(built_set, tmp_path, qtype)
    assert save(d, dict(rec), data)["valid"]                      # unmodified copy is valid
    a = rec["answer"]
    if qtype == "min_stops":
        wrong = a + 1
    elif qtype == "reroute_lines":
        wrong = a[::-1] if len(set(a)) > 1 else a + ["A"]
    else:
        other = sorted({v["text"] for v in data["layout"]["labels"].values()} - {a})
        wrong = other[0]
    rec["answer"] = data["question"]["answer"] = wrong
    r = save(d, rec, data)
    assert not r["valid"] and "answer_recomputed" in r["failed"]


def test_tampered_image_fails_schema(built_set, tmp_path):
    d, rec, data = one_task(built_set, tmp_path, "min_stops")
    p = d / rec["image"]
    p.write_bytes(p.read_bytes() + b"\0")
    r = save(d, rec, data)
    assert r["failed"] == ["schema"]
    assert "image hash differs from record" in r["details"]["schema"]["problems"]


def test_missing_image_fails_schema(built_set, tmp_path):
    d, rec, data = one_task(built_set, tmp_path, "min_stops")
    (d / rec["image"]).unlink()
    assert "image missing" in save(d, rec, data)["details"]["schema"]["problems"]


def test_unlabelled_origin_fails_names_visible(built_set, tmp_path):
    d, rec, data = one_task(built_set, tmp_path, "min_stops")
    del data["layout"]["labels"][data["question"]["meta"]["origin"]]
    r = save(d, rec, data)
    assert "names_visible" in r["failed"]


def test_extra_chip_fails_render_matches_data(built_set, tmp_path):
    d, rec, data = one_task(built_set, tmp_path, "min_stops")
    s = data["question"]["meta"]["origin"]
    data["layout"]["stations"][s]["stops"] = data["layout"]["stations"][s]["stops"] + ["ZZ"]
    assert "render_matches_data" in save(d, rec, data)["failed"]


def test_suspended_route_drawn_as_stopping_fails(built_set, tmp_path):
    """If the renderer forgot the suspension (chip drawn where trains do not stop), the check must notice."""
    d, rec, data = one_task(built_set, tmp_path, "min_stops")
    sc = data["service_change"]
    lay = data["layout"]
    gone = [(s, r) for s, r in lay["no_stop"] if s in lay["stations"]]
    assert sc and gone
    s, r = gone[0]
    lay["stations"][s]["stops"] = sorted(set(lay["stations"][s]["stops"]) | {r})
    assert "render_matches_data" in save(d, rec, data)["failed"]


def test_no_memory_trap_is_caught(built_set, tmp_path):
    d, rec, data = one_task(built_set, tmp_path, "min_stops")
    data["question"]["meta"]["normal_answer"] = rec["answer"]
    assert "memory_trap" in save(d, rec, data)["failed"]


def test_part_time_and_ambiguous_label_are_caught(built_set, tmp_path):
    d, rec, data = one_task(built_set, tmp_path, "min_stops")
    data["layout"]["part_time"] = [["X", "Y"]]
    data["layout"]["labels"][data["question"]["meta"]["dest"]]["ambiguous"] = True
    failed = save(d, rec, data)["failed"]
    assert "no_part_time_stops" in failed and "labels_unambiguous" in failed
