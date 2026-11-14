import pytest

from eval.extract import extract
from eval.prompt import build_prompt
from eval.score import is_correct


@pytest.mark.parametrize("response, answer_type, expected", [
    ("blah\nFINAL ANSWER: 42", "integer", 42),
    ("FINAL ANSWER: 7\nwait, recheck\nFINAL ANSWER: 9", "integer", 9),
    ("Final answer: **1,234.5 km**.", "number", 1234.5),
    ("FINAL ANSWER: −3", "integer", -3),
    ("FINAL ANSWER: 3.5", "integer", 3.5),
    ("FINAL ANSWER: $\\boxed{17}$", "integer", 17),
    ("FINAL ANSWER:\n\n  12 minutes", "integer", 12),
    ("FINAL ANSWER: (B) Central Station", "multiple_choice", "B"),
    ("FINAL ANSWER: c.", "multiple_choice", "C"),
    ("FINAL ANSWER: Option D", "multiple_choice", "D"),
    ("FINAL ANSWER: Central Station.", "label", "Central Station"),
    ("FINAL ANSWER: Alpha, Beta -> Gamma", "sequence", ["Alpha", "Beta", "Gamma"]),
    ('FINAL ANSWER: ["Alpha", "Beta"]', "sequence", ["Alpha", "Beta"]),
    ("FINAL ANSWER: A → B → C", "sequence", ["A", "B", "C"]),
    ("I think it is 42", "integer", None),
    ("", "label", None),
    ("FINAL ANSWER: none visible", "number", None),
])
def test_extract(response, answer_type, expected):
    assert extract(response, answer_type) == expected


def task(answer, answer_type, **kw):
    return {"task_id": "t", "question": "Q?", "answer": answer, "answer_type": answer_type, **kw}


@pytest.mark.parametrize("parsed, t, expected", [
    (104.9, task(100, "number", tolerance_rel=0.05), 1),
    (105.1, task(100, "number", tolerance_rel=0.05), 0),
    (0.0, task(0, "number", tolerance_rel=0.05), 1),
    (2.4, task(2.0, "number", tolerance_abs=0.5), 1),
    (2.6, task(2.0, "number", tolerance_abs=0.5), 0),
    (12, task(12, "integer"), 1),
    (12.5, task(12, "integer"), 0),
    ("b", task("B", "multiple_choice", options=["x", "y"]), 1),
    ("the Central  Station", task("Central Station", "label"), 1),
    ("Central", task("Central Station", "label"), 0),
    (["a", "B", "3"], task(["A", "b", 3], "sequence"), 1),
    (["A", "B"], task(["B", "A"], "sequence"), 0),
    (["A"], task(["A", "B"], "sequence"), 0),
    (None, task(1, "integer"), 0),
])
def test_is_correct(parsed, t, expected):
    assert is_correct(parsed, t) == expected


def test_prompt_states_tolerance_like_the_checker():
    p = build_prompt(task(100.0, "number", tolerance_rel=0.05))
    assert "±5%" in p and p.rstrip().endswith("FINAL ANSWER: <answer>")
    assert "±0.5 " in build_prompt(task(2.0, "number", tolerance_abs=0.5))


def test_prompt_lists_options():
    p = build_prompt(task("B", "multiple_choice", options=["Red line", "Blue line"]))
    assert "A. Red line\nB. Blue line" in p


def test_prompt_mc_without_options_fails():
    with pytest.raises(ValueError):
        build_prompt(task("A", "multiple_choice"))
