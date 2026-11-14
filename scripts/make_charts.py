"""Charts for the latest test run and the model results.

Run:  python -m pytest tests eval/tests --junitxml=docs/charts/junit.xml && python scripts/make_charts.py
"""
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "charts"
GREEN, GREY, RED, NAVY = "#00933C", "#A7A9AC", "#EE352E", "#1E2933"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})

# ---- 1. tests by file
counts = defaultdict(lambda: {"passed": 0, "xfail": 0, "failed": 0})
for tc in ET.parse(OUT / "junit.xml").getroot().iter("testcase"):
    name = tc.get("classname", "").replace(".", "/") + ".py"
    if tc.find("failure") is not None or tc.find("error") is not None:
        counts[name]["failed"] += 1
    elif tc.find("skipped") is not None:
        counts[name]["xfail"] += 1
    else:
        counts[name]["passed"] += 1
files = sorted(counts, key=lambda f: (not f.startswith("eval"), f), reverse=True)
p = [counts[f]["passed"] for f in files]
x = [counts[f]["xfail"] for f in files]
fl = [counts[f]["failed"] for f in files]
tot = {k: sum(c[k] for c in counts.values()) for k in ("passed", "xfail", "failed")}

fig, ax = plt.subplots(figsize=(10, 6))
ax.barh(files, p, color=GREEN, label=f"passed ({tot['passed']})")
ax.barh(files, x, left=p, color=GREY, label=f"expected failure, xfail ({tot['xfail']})")
ax.barh(files, fl, left=[a + b for a, b in zip(p, x)], color=RED, label=f"failed ({tot['failed']})")
for i, (a, b) in enumerate(zip(p, x)):
    ax.text(a + b + 0.3, i, f"{a}" + (f" + {b} xfail" if b else ""), va="center", fontsize=10, color=NAVY)
ax.set_title(f"Test suite re-run: {tot['passed']} passed, {tot['failed']} failed, {tot['xfail']} expected failures",
             loc="left", fontsize=14, color=NAVY, fontweight="bold")
ax.set_xlabel("tests")
ax.spines[["top", "right"]].set_visible(False)
ax.legend(loc="lower right", frameon=False)
fig.tight_layout()
fig.savefig(OUT / "tests_by_file.png", dpi=150)

# ---- 2. model accuracy across runs on the final 10 tasks
def acc(folder):
    a = json.loads((ROOT / "results" / folder / "run_config.json").read_text())["accuracy"]
    return {m.split("/")[1]: v["correct"] for m, v in a.items() if v["n"]}

runs = [("Haiku low", acc("final_haiku_low").get("claude-haiku-5.5"), GREY),
        ("Haiku medium", acc("final_haiku_medium").get("claude-haiku-5.5"), GREY),
        ("Haiku high\n(reported)", acc("final")["claude-haiku-5.5"], RED),
        ("Luna high\n(reported)", acc("final")["gpt-6-luna"], GREEN)]
rerun = OUT / "docker_rerun_run_config.json"  # run_config.json of the clean-copy Docker reproduction
if rerun.exists():
    a = json.loads(rerun.read_text())["accuracy"]
    runs += [("Haiku high\n(Docker rerun)", a["anthropic/claude-haiku-5.5"]["correct"], "#F4A3A0"),
             ("Luna high\n(Docker rerun)", a["openai/gpt-6-luna"]["correct"], "#7FC99D")]
fig, ax = plt.subplots(figsize=(10, 5.5))
bars = ax.bar([r[0] for r in runs], [r[1] for r in runs], color=[r[2] for r in runs])
for b, r in zip(bars, runs):
    ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.15, f"{r[1]}/10", ha="center", fontsize=12,
            color=NAVY, fontweight="bold")
ax.set_ylim(0, 10.5)
ax.set_ylabel("correct answers (of 10)")
ax.set_title("Final 10 tasks: correct answers by model, effort and run", loc="left", fontsize=14, color=NAVY,
             fontweight="bold")
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(OUT / "model_accuracy.png", dpi=150)
print(tot)
