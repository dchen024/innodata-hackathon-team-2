"""validate/schema.py vs the organizers' tools/check_submission.py: a record our schema accepts must not be
FAILed by the judges' checker (soundness). Where the schema is looser, the case is a strict xfail."""
from __future__ import annotations

import json
import sys

import pytest

from tests.conftest import ROOT
from validate.schema import check_record

sys.path.insert(0, str(ROOT / "tools"))
import check_submission as cs  # noqa: E402

BASE = dict(task_id="t1", image="images/t1.png", seed=1, generator_version="x", question_type="q")


def loose(reason):
    return pytest.mark.xfail(strict=True, reason=f"schema.py looser than check_submission.py: {reason}")


CASES = [
    pytest.param(dict(answer=6, answer_type="integer", question="How many?"), id="integer"),
    pytest.param(dict(answer=True, answer_type="integer", question="How many?"), id="integer-bool"),
    pytest.param(dict(answer="6", answer_type="integer", question="How many?"), id="integer-str"),
    pytest.param(dict(answer=["A", "7"], answer_type="sequence", question="Which?"), id="sequence"),
    pytest.param(dict(answer="A", answer_type="sequence", question="Which?"), id="sequence-str"),
    pytest.param(dict(answer="Borough Hall", answer_type="label", question="Where?"), id="label"),
    pytest.param(dict(answer=3.5, answer_type="number", tolerance_rel=0.05, question="within 5%, what?"),
                 id="number-tol"),
    pytest.param(dict(answer=3.5, answer_type="number", question="What?"), id="number-no-tol"),
    pytest.param(dict(answer=3.5, answer_type="number", tolerance_rel=0.05, tolerance_abs=0.1,
                      question="within 5%?"), id="number-two-tol"),
    pytest.param(dict(answer=4, answer_type="number", question="What?"), id="number-whole-no-tol"),
    pytest.param(dict(answer="B", answer_type="multiple_choice", options=["x", "y"], question="Pick"), id="mc"),
    pytest.param(dict(answer=1, answer_type="ranking", question="?"), id="bad-type"),
    pytest.param(dict(answer=1, question="?"), id="no-type"),
    # schema gaps (subway only emits integer/label/sequence, so these are latent)
    pytest.param(dict(answer=[], answer_type="sequence", question="Which?"), id="sequence-empty",
                 marks=loose("empty sequence accepted")),
    pytest.param(dict(answer=42, answer_type="label", question="Where?"), id="label-int",
                 marks=loose("non-string label accepted")),
    pytest.param(dict(answer="B", answer_type="multiple_choice", question="Pick"), id="mc-no-options",
                 marks=loose("multiple_choice without options accepted")),
    pytest.param(dict(answer=3.5, answer_type="number", tolerance_rel=5, question="within 5%?"), id="tol-rel-pct",
                 marks=loose("tolerance_rel >= 1 (a percentage, not a fraction) accepted")),
    pytest.param(dict(answer="abc", answer_type="number", question="What?"), id="number-str-crash"),
]


def checker_fails(tmp_path, rec):
    d = tmp_path / "tasks"
    (d / "images").mkdir(parents=True)
    (d / "images" / "t1.png").write_bytes(b"\x89PNG fake")
    (d / "tasks.jsonl").write_text(json.dumps(rec) + "\n")
    rep = cs.Report()
    cs.check_tasks(rep, cs.Submission(tmp_path), "tasks", 1, "")
    return [m for _, lvl, m in rep.items if lvl == "FAIL"]


@pytest.mark.parametrize("extra", CASES)
def test_schema_pass_implies_checker_pass(tmp_path, extra):
    rec = {**BASE, **extra}
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "t1.png").write_bytes(b"\x89PNG fake")
    ours = check_record(rec, tmp_path)["schema"]
    theirs = checker_fails(tmp_path / "sub", rec)
    if ours["passed"]:
        assert not theirs, f"schema passed but the judges' checker FAILs: {theirs}"


def test_schema_rejects_obviously_bad_records(tmp_path):
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "t1.png").write_bytes(b"x")
    bad = [dict(answer=True, answer_type="integer"), dict(answer="A", answer_type="sequence"),
           dict(answer=3.5, answer_type="number"), dict(answer=1, answer_type="ranking"),
           dict(answer=3.5, answer_type="number", tolerance_rel=0.05)]          # tolerance not stated in question
    for b in bad:
        assert not check_record({**BASE, "question": "What?", **b}, tmp_path)["schema"]["passed"], b
    missing = {k: v for k, v in {**BASE, "question": "q", "answer": 1, "answer_type": "integer"}.items() if k != "seed"}
    assert "missing seed" in check_record(missing, tmp_path)["schema"]["problems"]


def test_built_records_pass_both(built_set):
    """The real built pilot2 folder passes the judges' task-file checks with no FAIL."""
    rep = cs.Report()
    cs.check_tasks(rep, cs.Submission(built_set["dir"].parent), built_set["dir"].name, 12, "")
    assert [m for _, lvl, m in rep.items if lvl == "FAIL"] == []
    for r in built_set["records"]:
        assert check_record(r, built_set["dir"])["schema"]["passed"]
