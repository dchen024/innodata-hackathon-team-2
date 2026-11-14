"""Family interface for the task factory.

A *family* is one kind of real transportation visual (e.g. a transit map, a timetable, a route diagram).
Every family turns (seed, level, question_type, style) into:

    data      structured data, saved as JSON; the single source of truth
    image     rendered by code from `data` only (never by an AI image model)
    question  text sent to the model, plus a reference answer computed from `data` by code

The core pipeline (build -> validate -> eval) never needs to know which family it is handling.
To add a family: subclass `Family` in generator/families/<name>.py, register it in
generator/families/__init__.py, and add its render checks to validate/families/<name>.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ANSWER_TYPES = ("number", "integer", "label", "multiple_choice", "sequence")


@dataclass
class Question:
    question_type: str
    question: str                    # exactly as sent to the model; must state any tolerance
    answer: Any                      # number, label, option letter, or list
    answer_type: str                 # one of ANSWER_TYPES
    tolerance_rel: float | None = None   # non-integer numbers: exactly one of rel / abs
    tolerance_abs: float | None = None
    options: list[str] | None = None     # multiple_choice only, in letter order
    meta: dict = field(default_factory=dict)


class NoValidQuestion(Exception):
    """The sampled data cannot support the requested question type; the family should resample."""


class Family:
    name: str = "base"
    version: str = "0.0.0"
    question_types: list[str] = []
    styles: list[str] = []
    levels: list[int] = [1, 2, 3]
    references: dict[str, list[str]] = {}   # style -> 1-2 real-world examples this style imitates

    def generate(self, seed: int, level: int, question_type: str, style: str) -> tuple[dict, Question]:
        """Deterministically sample data that supports `question_type`, and build the question."""
        raise NotImplementedError

    def render(self, data: dict, png_path: str) -> dict:
        """Render `data` to `png_path`. Return a layout dict of what was drawn, for the render checks."""
        raise NotImplementedError
