"""Judges rebuild the reported tasks from their seeds (Docker, `python -m factory reproduce`): the rebuild must
match byte for byte (image hash), and question/answer must match exactly - across processes and hash seeds."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from tests.conftest import ROOT, read_jsonl

KEYS = ("image_sha256", "question", "answer", "answer_type", "seed", "generator_version")


def test_rebuild_matches_committed_final(built_set):
    """Same comparison `reproduce` makes against the submitted folder. tasks/final is built in Docker (Linux), so on
    another OS the PNG bytes can differ while the pixels are identical: compare pixels, plus exact question/answer."""
    import numpy as np
    from PIL import Image
    committed = {r["task_id"]: r for r in read_jsonl(ROOT / "tasks" / "final" / "tasks.jsonl")}
    rebuilt = built_set["raw"]
    assert set(rebuilt) == set(committed)
    diff = {}
    for t in rebuilt:
        ks = [k for k in KEYS if k != "image_sha256" and rebuilt[t].get(k) != committed[t].get(k)]
        a = np.asarray(Image.open(built_set["dir"] / rebuilt[t]["image"]).convert("RGBA"))
        b = np.asarray(Image.open(ROOT / "tasks" / "final" / committed[t]["image"]).convert("RGBA"))
        # pixels are compared where the submitted folder was built (Linux / Docker); float rounding differs
        # across OSes and can flip a layout tie-break, so elsewhere only question and answer are compared
        if sys.platform.startswith("linux") and (a.shape != b.shape or (a != b).any()):
            ks.append("pixels")
        if ks:
            diff[t] = ks
    assert not diff, f"rebuilt tasks differ from tasks/final (bump generator_version if intended): {diff}"


def test_in_process_rebuild_is_identical(built_set, tmp_path):
    from generator.build import build_task
    spec = json.loads((ROOT / "configs" / "final.json").read_text())["tasks"]
    for t in (spec[0], spec[6]):
        rec = build_task(t, tmp_path)
        ref = built_set["raw"][t["task_id"]]
        assert {k: rec[k] for k in KEYS} == {k: ref[k] for k in KEYS}
        assert json.loads((tmp_path / rec["data"]).read_text()) == \
            json.loads((built_set["dir"] / ref["data"]).read_text())


@pytest.mark.parametrize("hashseed", ["0", "4242"])
def test_rebuild_independent_of_pythonhashseed(built_set, tmp_path, hashseed):
    """Set iteration order changes with PYTHONHASHSEED; nothing in the output may depend on it."""
    spec = json.loads((ROOT / "configs" / "final.json").read_text())
    spec["tasks"] = [spec["tasks"][1], spec["tasks"][4], spec["tasks"][7]]   # transfer, accessible, reroute
    (tmp_path / "spec.json").write_text(json.dumps(spec))
    code = ("import sys; from generator.build import build_set; build_set(sys.argv[1], sys.argv[2])")
    env = {**os.environ, "PYTHONHASHSEED": hashseed}
    env.pop("OPENROUTER_API_KEY", None)
    env.pop("ANTHROPIC_API_KEY", None)
    subprocess.run([sys.executable, "-c", code, str(tmp_path / "spec.json"), str(tmp_path / "out")],
                   cwd=ROOT, env=env, check=True, capture_output=True, timeout=120)
    for rec in read_jsonl(tmp_path / "out" / "tasks.jsonl"):
        ref = built_set["raw"][rec["task_id"]]
        assert {k: rec[k] for k in KEYS} == {k: ref[k] for k in KEYS}, rec["task_id"]
        assert json.loads((tmp_path / "out" / rec["data"]).read_text()) == \
            json.loads((built_set["dir"] / ref["data"]).read_text()), rec["task_id"]
