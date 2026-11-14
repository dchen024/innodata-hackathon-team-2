"""Performance graph over repeated runs of the reported task set.

Reads run 1 (results/final for high effort, results/final_<model>_<effort> otherwise) and runs 2..N
(results/run<N>_<model>_<effort>), then writes docs/performance.png and docs/performance.json:
  left   accuracy per model and reasoning effort: one dot per run, mean and min-max range
  right  per-task solve rate at high effort, both models (where the difficulty sits)
Usage: python scripts/plot_runs.py            (writes docs/performance.png and .json)
       python scripts/plot_runs.py --slide OUT  (compact copy for a slide: smaller canvas, no footnote)
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODELS = {"haiku": ("Claude Haiku 5.5", "anthropic/claude-haiku-5.5", "#C8643B"),
          "luna": ("GPT-6 Luna", "openai/gpt-6-luna", "#2A7F87")}
EFFORTS = ["low", "medium", "high"]


def folder(run: int, m: str, e: str) -> Path:
    if run == 1:
        return ROOT / "results" / ("final" if e == "high" else f"final_{m}_{e}")
    return ROOT / "results" / f"run{run}_{m}_{e}"


def load():
    runs = sorted({1} | {int(p.name.split("_")[0][3:]) for p in (ROOT / "results").glob("run*_*_*")
                         if (p / "responses.csv").exists()})
    data = {}                                    # (model, effort) -> list of {task: correct} per run
    for m, (_, mid, _) in MODELS.items():
        for e in EFFORTS:
            per_run = []
            for r in runs:
                f = folder(r, m, e) / "responses.csv"
                if not f.exists():
                    continue
                rows = [x for x in csv.DictReader(open(f)) if x["model"] == mid]
                bad = [x for x in rows if x["status"] != "ok" or x["finish_reason"] != "stop" or x["error"]]
                assert not bad, f"unclean rows in {f}"
                per_run.append({x["task_id"]: x["correct"] == "1" for x in rows})
            data[(m, e)] = per_run
    return runs, data


def main(slide_out: str | None = None):
    runs, data = load()
    tasks = sorted(next(iter(data.values()))[0])
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.6, 4.0) if slide_out else (13, 5.2), gridspec_kw=dict(width_ratios=[1, 1.35]))
    fig.patch.set_facecolor("white")
    summary = {"runs": runs, "accuracy": {}, "high_effort_solve_rate": {}}

    # left: accuracy by effort, dots per run + mean and range
    rng = np.random.default_rng(0)
    for k, (m, (name, _, color)) in enumerate(MODELS.items()):
        means = []
        for i, e in enumerate(EFFORTS):
            scores = [sum(r.values()) for r in data[(m, e)]]
            x = i + (k - 0.5) * 0.28
            a1.scatter(x + rng.uniform(-0.05, 0.05, len(scores)), scores, s=22, color=color, alpha=0.45, lw=0, zorder=2)
            mu = float(np.mean(scores))
            a1.plot([x, x], [min(scores), max(scores)], color=color, lw=1.6, alpha=0.8, zorder=2)
            a1.scatter([x], [mu], s=70, color=color, edgecolor="white", lw=1.2, zorder=3)
            means.append(mu)
            summary["accuracy"][f"{m}_{e}"] = dict(scores=scores, mean=round(mu, 2), min=min(scores), max=max(scores))
        a1.plot([i + (k - 0.5) * 0.28 for i in range(3)], means, color=color, lw=1.4, zorder=1, label=name)
    a1.set_xticks(range(3), ["low", "medium", "high"])
    a1.set_xlabel("Reasoning effort")
    a1.set_ylabel("Correct answers (of 10)")
    a1.set_ylim(0, 10.5)
    a1.set_title(f"Accuracy over {len(runs)} runs" + ("" if slide_out else " (dots = runs, line = mean)"), fontsize=12,
                 loc="left")
    a1.legend(frameon=False, loc="lower right")

    # right: per-task solve rate at high effort
    w = 0.38
    for k, (m, (name, _, color)) in enumerate(MODELS.items()):
        per_run = data[(m, "high")]
        rate = [100 * np.mean([r[t] for r in per_run]) for t in tasks]
        summary["high_effort_solve_rate"][m] = dict(zip(tasks, [round(x, 1) for x in rate]))
        a2.bar(np.arange(len(tasks)) + (k - 0.5) * w, rate, width=w, color=color, label=name)
    types = {json.loads(l)["task_id"]: json.loads(l)["question_type"] for l in open(ROOT / "tasks/final/tasks.jsonl")}
    short = {"accessible_route": "wheel-\nchair", "reroute_lines": "re-\nroute", "transfer_station": "trans-\nfer",
             "min_stops": "fewest\nstops"}
    a2.set_xticks(range(len(tasks)), [f"{t}\n{short.get(types[t], types[t])}" for t in tasks], fontsize=8.5)
    a2.set_ylabel("Solved at high effort (% of runs)")
    a2.set_ylim(0, 118)
    a2.set_yticks(range(0, 101, 20))
    a2.set_title("Per-task solve rate, high effort" if slide_out else
                 "Where the difficulty sits: per-task solve rate, high effort", fontsize=12, loc="left")
    a2.legend(frameon=False, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.0))
    for ax in (a1, a2):
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.grid(axis="y", color="#e5e5e5", lw=0.8)
        ax.set_axisbelow(True)
    if slide_out:
        fig.tight_layout()
        fig.savefig(slide_out, dpi=220)
        print(f"wrote {slide_out}")
        return
    fig.text(0.01, 0.005, "Temperature 0 is sent on every call; OpenRouter routes no endpoint that applies it with reasoning "
             "enabled, so runs vary. 10 submitted tasks, identical images and prompts in every run.",
             fontsize=8, color="#555555")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    out = ROOT / "docs" / "performance.png"
    fig.savefig(out, dpi=170)
    (ROOT / "docs" / "performance.json").write_text(json.dumps(summary, indent=1))
    print(f"wrote {out.relative_to(ROOT)} from runs {runs}")
    for k, v in summary["accuracy"].items():
        print(f"  {k:13s} mean {v['mean']:.1f}  range {v['min']}-{v['max']}  {v['scores']}")


if __name__ == "__main__":
    main(sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--slide" else None)
