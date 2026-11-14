"""Live demo: one task, both models x low/medium/high in parallel, then an HTML report.

    python -m factory demo --task t08 --out results/demo_t08          # a submitted task (tasks/final)
    python -m factory demo --seed 12345 --question-type accessible_route --out results/demo_fresh

A fresh seed is built and validated first. The six calls run at once (about a minute at high effort). The report
(<out>/report.html) shows the map, the question, the reference trip computed by code, the automatic checks, and every
model's answer and reasoning. It opens in the browser unless --no-open is given.
"""
from __future__ import annotations

import base64
import html
import json
import shutil
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

EFFORTS = ("low", "medium", "high")
ROUTE_COLORS = {**dict.fromkeys("ACE", "#0039A6"), **dict.fromkeys("BDFM", "#FF6319"), "G": "#6CBE45",
                **dict.fromkeys("JZ", "#996633"), "L": "#A7A9AC", **dict.fromkeys("NQRW", "#FCCC0A"),
                **dict.fromkeys("123", "#EE352E"), **dict.fromkeys("456", "#00933C"), "7": "#B933AD",
                "S": "#808183", "GS": "#808183"}


def _prepare(a, out: Path) -> Path:
    """Return a task folder holding exactly one task."""
    tdir = out / "tasks"
    if a.task:
        src = Path(a.tasks)
        rec = next(json.loads(l) for l in (src / "tasks.jsonl").read_text().splitlines()
                   if l.strip() and json.loads(l)["task_id"] == a.task)
        for sub in ("images", "data"):
            (tdir / sub).mkdir(parents=True, exist_ok=True)
        shutil.copy(src / rec["image"], tdir / rec["image"])
        shutil.copy(src / rec["data"], tdir / rec["data"])
        (tdir / "tasks.jsonl").write_text(json.dumps(rec) + "\n")
        checks = src / "checks.json"
        if checks.exists():
            (tdir / "checks.json").write_text(json.dumps({a.task: json.loads(checks.read_text())[a.task]}))
        return tdir
    from generator.build import build_set
    from validate.run import validate_set
    spec = dict(set="demo", tasks=[dict(task_id=f"demo_{a.seed}", family=a.family, seed=a.seed, level=a.level,
                                        question_type=a.question_type, style=a.style)])
    out.mkdir(parents=True, exist_ok=True)
    (out / "spec.json").write_text(json.dumps(spec, indent=1))
    build_set(str(out / "spec.json"), str(tdir))
    validate_set(str(tdir))
    return tdir


def _chip(r: str) -> str:
    c = ROUTE_COLORS.get(r, "#555")
    fg = "#111" if c == "#FCCC0A" else "#fff"
    return f'<span class="chip" style="background:{c};color:{fg}">{html.escape("S" if r == "GS" else r)}</span>'


def _seq(ans) -> str:
    if isinstance(ans, list):
        return " → ".join(_chip(str(x)) for x in ans)
    return f"<b>{html.escape(str(ans))}</b>"


def _reasoning(raw: dict) -> str:
    try:
        msg = raw["response"]["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return ""
    return msg.get("reasoning") or ""


def write_report(out: Path, tdir: Path, models: list[str]) -> Path:
    rec = json.loads((tdir / "tasks.jsonl").read_text().splitlines()[0])
    tid = rec["task_id"]
    data = json.loads((tdir / rec["data"]).read_text())
    labels = data.get("layout", {}).get("labels", {})
    name = lambda sid: labels.get(sid, {}).get("text", sid)
    meta = data["question"]["meta"]
    img = base64.b64encode((tdir / rec["image"]).read_bytes()).decode()
    checks = {}
    if (tdir / "checks.json").exists():
        checks = json.loads((tdir / "checks.json").read_text()).get(tid, {})
    trip = (meta.get("trips") or [[]])[0]
    legs = "".join(f"<li>{_chip(r)} {html.escape(name(a))} → {html.escape(name(b))}</li>" for r, a, b in trip)
    accepted = meta.get("accepted_answers") or []
    normal = meta.get("normal_answer")
    check_items = "".join(f'<span class="pill {"ok" if v.get("passed") else "bad"}">{html.escape(k)}</span>'
                          for k, v in checks.get("details", {}).items() if isinstance(v, dict) and "passed" in v)

    cells, score = [], {}
    for m in models:
        slug = m.replace("/", "__")
        row = []
        for e in EFFORTS:
            f = out / f"results_{e}" / "raw" / slug / f"{tid}.json"
            if not f.exists():
                row.append('<td class="cell"><i>no reply</i></td>')
                continue
            r = json.loads(f.read_text())
            ok = r.get("correct") == 1
            score[(m, e)] = ok
            reasoning = _reasoning(r)
            row.append(
                f'<td class="cell {"right" if ok else "wrong"}"><div class="verdict">{"✓ correct" if ok else "✗ wrong"}'
                f'</div><div class="ans">{_seq(r.get("parsed")) if r.get("parsed") is not None else "<i>no answer</i>"}'
                f'</div><div class="meta">{r.get("latency_s") or 0:.0f}s · ${r.get("cost") or 0:.4f}</div>'
                + (f'<details><summary>reasoning</summary><pre>{html.escape(reasoning)}</pre></details>' if reasoning
                   else "")
                + f'<details><summary>reply</summary><pre>{html.escape(r.get("content") or "")}</pre></details></td>')
        nice = {"anthropic/claude-haiku-5.5": "Claude Haiku 5.5", "openai/gpt-6-luna": "GPT-6 Luna"}.get(m, m)
        cells.append(f"<tr><th>{html.escape(nice)}</th>{''.join(row)}</tr>")

    notice = "<br>".join(html.escape(x) for x in data.get("service_change", {}).get("notice", []))
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>Demo {html.escape(tid)}</title><style>
body{{font:15px/1.45 -apple-system,system-ui,sans-serif;margin:0;background:#f4f4f1;color:#1a1a1a}}
header{{background:#fff;padding:14px 24px;border-bottom:1px solid #ddd}} h1{{margin:0;font-size:22px}}
.sub{{color:#666;font-size:13px}} main{{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:18px;padding:18px 24px}}
.card{{background:#fff;border:1px solid #e2e2dd;border-radius:10px;padding:16px}} img{{width:100%;border-radius:6px}}
.notice{{background:#FCCC0A;padding:10px 12px;border-radius:6px;font-weight:500;margin-bottom:10px}}
.chip{{display:inline-block;min-width:22px;height:22px;border-radius:11px;text-align:center;font-weight:700;line-height:22px;padding:0 4px;margin:0 1px}}
h2{{font-size:12px;letter-spacing:.08em;color:#666;text-transform:uppercase;margin:14px 0 6px}}
ul{{margin:4px 0;padding-left:18px}} .pill{{display:inline-block;font-size:12px;padding:2px 8px;border-radius:10px;margin:2px}}
.ok{{background:#e3f3e6;color:#1d6b33}} .bad{{background:#fbe3e1;color:#a2271c}}
table{{width:100%;border-collapse:separate;border-spacing:8px}} th{{text-align:left;font-size:14px;width:120px}}
thead th{{font-size:12px;text-transform:uppercase;color:#666;letter-spacing:.06em}}
.cell{{background:#fafaf8;border:1px solid #e2e2dd;border-radius:8px;padding:10px;vertical-align:top}}
.right{{border-color:#7cc08f;background:#f1faf3}} .wrong{{border-color:#e39a92;background:#fdf3f2}}
.verdict{{font-weight:700;margin-bottom:4px}} .right .verdict{{color:#1d6b33}} .wrong .verdict{{color:#a2271c}}
.meta{{color:#777;font-size:12px;margin-top:4px}} pre{{white-space:pre-wrap;font-size:12px;max-height:320px;overflow:auto;background:#fff;padding:8px;border-radius:6px}}
summary{{cursor:pointer;color:#0b63c4;font-size:13px;margin-top:4px}}
</style></head><body><header><h1>Live demo · {html.escape(tid)} · {html.escape(rec.get("question_type", ""))}</h1>
<div class="sub">{html.escape(data.get("layout", {}).get("region", ""))} · seed {rec.get("seed")} · generator {html.escape(str(rec.get("generator_version")))} ·
temperature 0 sent · both models × low / medium / high · {sum(score.values())}/{len(score)} correct</div></header>
<main><div class="card"><img src="data:image/png;base64,{img}" alt="generated subway map"></div>
<div><div class="card"><div class="notice">{notice}</div><div>{html.escape(rec["question"])}</div>
<h2>Reference answer (computed by code)</h2><div>{_seq(rec["answer"])}</div>
{"<div class='sub'>Also accepted: " + " · ".join(_seq(x) for x in accepted if x != rec["answer"]) + "</div>" if len(accepted) > 1 else ""}
{"<h2>Reference trip</h2><ul>" + legs + "</ul>" if legs else ""}
{"<div class='sub'>Normal-service answer (the memory trap): " + " / ".join(_seq(x) for x in normal) + "</div>" if normal else ""}
<h2>Automatic checks</h2><div>{check_items or "<i>none recorded</i>"}</div></div>
<div class="card" style="margin-top:18px"><table><thead><tr><th></th><th>low</th><th>medium</th><th>high</th></tr></thead>
{"".join(cells)}</table></div></div></main></body></html>"""
    path = out / "report.html"
    path.write_text(page)
    return path


def run_demo(a) -> None:
    from eval.run import evaluate
    out = Path(a.out)
    tdir = _prepare(a, out)
    models = a.models.split(",")
    if not a.no_eval:
        with ThreadPoolExecutor(max_workers=3) as ex:
            list(ex.map(lambda e: evaluate(str(tdir), str(out / f"results_{e}"), models=models,
                                           max_tokens=a.max_tokens, workers=len(models), effort=e, strict=False),
                        EFFORTS))
    path = write_report(out, tdir, models)
    print(f"report: {path.resolve()}")
    if not a.no_open:
        webbrowser.open(path.resolve().as_uri())
