# NYC Subway Weekend Task Factory — Innodata Hackathon, Track 2

A pipeline that turns the MTA's public subway timetable into **realistic, MTA-style schematic maps with a weekend
service change** and asks a commuter question about each one ("No 2 or 3 trains between Park Place and Wall St —
which services do you ride from Delancey St to Franklin St?"). Every image is drawn by code from structured data,
every answer is computed by code from the same data, and independent checks confirm the image shows what the answer
assumes. On the final 10 tasks Claude Haiku 5.5 scores 5/10 and GPT-6 Luna 8/10 at high reasoning; one task
(t05) defeats every run.

## Reported folders

- Tasks: `tasks/final`
- Results: `results/final`

## Problem statement

People plan real trips from transit maps, and the hardest moment is a weekend service change: a notice says a line
is suspended or a station is closed, and the rider has to re-plan using what the map shows: which services stop
where (express vs local), where transfers are, which stations are accessible. A wrong but confident answer sends
someone to a closed platform. We test whether multimodal models can **read a dense transit diagram and re-plan
correctly when the usual answer (memorised from the real NYC subway) is wrong**.

## How the pipeline works

```
MTA GTFS + station list ─► subway graph (data/*.json)
seed + spec ─► scenario: map window, weekend service change, origin/destination, question type
           ─► renderer: schematic map PNG (lines, stop markers, transfer pills, notice, accessibility symbols)
           ─► answer computed by code on the modified network (generator/families/subway/family.py)
           ─► validate/: independent re-computation, render-vs-data, OCR, legibility, uniqueness, clearance
           ─► validate/review.py: adversarial LLM audit (Claude Opus 5.5) of every task
           ─► eval/: OpenRouter calls, answer extraction, scoring, report
```

| Folder | Contents |
|---|---|
| `generator/families/subway/build_graph.py` | Builds `data/subway_graph.json` (weekday) and `data/subway_graph_saturday.json` from the MTA GTFS feed and the data.ny.gov station list: per-route stop sequences, median run times, transfer groups (MTA complex ids + GTFS transfers), accessibility, per-station trip counts (part-time stops) |
| `generator/families/subway/layout.py` | Octilinear schematic layout computed from real coordinates (our own algorithm, no published map traced) |
| `generator/families/subway/render.py` | MTA-style renderer: ribbon lines, a lettered marker on each line that stops (express lines pass with no marker), hollow markers for part-time stops, one-row transfer pills, connectors between joined stations, accessibility symbols, service-change overlay and notice, legend; plus a pixel audit for overlaps, mislabelled stations and markers sitting on lines that don't serve them |
| `generator/families/subway/family.py` | Scenario sampling, trip planner (Dijkstra over station × route × arrived-by-train states), question types |
| `generator/build.py` | spec → `tasks.jsonl`, `images/`, `data/` |
| `validate/` | `schema.py` (record format), `families/subway.py` (all task checks), `run.py`, `review.py` (adversarial reviewer) |
| `eval/` | OpenRouter client, prompt, extraction, scoring, runner |
| `factory/` | CLI: `build`, `validate`, `eval`, `reproduce`, `fresh` |
| `tests/`, `eval/tests/` | 94 tests: reproducibility, planner vs validator agreement, validator catches bad tasks, service-change semantics, schema vs the organizers' checker, layout, render audit, submission format |
| `docs/maps/nyc_subway_full_system.pdf` | The whole system rendered by the same code (weekday) |

### Question types

| Type | What the model must do | Answer |
|---|---|---|
| `reroute_lines` | Fewest transfers, then fewest stops, from A to B under the change; list the services ridden | sequence; any service running between the same two stations on a leg is accepted (`accepted_answers`) |
| `accessible_route` | Same, but boarding, alighting and transfers only at stations with the accessibility symbol | sequence (same acceptance rule) |
| `transfer_station` | The single station where the best one-transfer trip changes trains | station name as printed |
| `min_stops` | Fewest station stops from A to B (transfers allowed, free) | integer |

Every question states the rules: walking between stations joined on the map counts as a transfer, and the trip ends
when a train arrives at the destination itself.

## Project structure

```
innodata-hackathon-team-2/
├── README.md
├── Dockerfile                    Python + Tesseract OCR + fixed fonts
├── requirements.txt
├── .env.example                  template for OPENROUTER_API_KEY (copy to .env, never committed)
│
├── configs/
│   ├── pilot.json                pilot 1 spec (12 tasks)
│   ├── pilot2.json               pilot 2 spec (12 tasks)
│   ├── candidates.json, cand_pool.json   candidate pools for the final selection
│   └── final.json                final spec: the 10 reported tasks (seeds, levels, types, styles)
│
├── data/
│   ├── subway_graph.json         weekday service graph
│   ├── subway_graph_saturday.json  weekend graph used by every task
│   └── nyc_boroughs.geojson      NYC Open Data shorelines (land/water)
│
├── docs/maps/
│   └── nyc_subway_full_system.pdf
│
├── generator/                    makes the maps and questions
│   ├── base.py                   Family interface
│   ├── build.py                  spec → tasks/<set>/
│   └── families/subway/
│       ├── build_graph.py        MTA GTFS → subway graph
│       ├── layout.py             octilinear schematic layout
│       ├── render.py             MTA-style map renderer + pixel audit
│       └── family.py             question types and answers
│
├── validate/                     checks every task before it is used
│   ├── run.py, schema.py         task-record and answer checks
│   ├── families/subway.py        render-vs-data, OCR, label clearance
│   └── review.py                 adversarial AI reviewer
│
├── eval/                         evaluates the models (the agents under test)
│   ├── prompt.py                 prompt sent with each map
│   ├── openrouter.py             API client with retries
│   ├── extract.py                pulls out the FINAL ANSWER
│   ├── score.py                  marks each answer right or wrong
│   ├── run.py                    runs every model × task, writes results/
│   └── tests/                    pytest suite (API faked)
│
├── factory/__main__.py           command line
├── scripts/haiku_effort_sweep.sh exact commands for the reported runs
├── tests/                        pytest suite: reproducibility, planner vs validator, render audit, format
├── tasks/final/                  the 10 reported tasks (built in Docker); pilot1/, pilot2/, candidates/ too
├── results/final/                reported run (both models, high); final_haiku_low/, final_haiku_medium/,
│                                 pilot1/, pilot2/, cand_*/ (earlier rounds)
├── slides/                       presentation
└── tools/check_submission.py     organizers' format checker
```

How the pieces connect:

```
configs → generator → tasks/ → validate → eval → results/
          (draw + ask)          (check)    (test models)
```

## How the tasks were made hard and why the models failed

- **Memory trap by construction.** A scenario is accepted only if the normal-service answer is different (stored as
  `normal_answer` in each task's data). A model that answers from memory of the NYC subway, or ignores the notice,
  is wrong.
- **Express vs local is read from markers.** A line has a lettered marker only where that service stops; an express
  line passes local stations with no marker. Planning the fewest stops needs this (t06: hop on the 4 express for one
  stop to skip Hoyt St — staying on the 2/3 is one stop longer).
- **Station closures make trains run through.** Counting stops or choosing transfers must skip the closed station.
- **Accessibility symbols restrict transfers.** Wheelchair routes must change only at stations with the symbol, so
  the usual transfer is often illegal.
- **Multi-leg planning on a dense map** (up to 3 rides), with complexes drawn as one-row pills joined by connectors.

Failure patterns in the final run (see the hand check below):
- **Miscounting stops / missing an express hop** — t05: every run wrong (Haiku 2 at all efforts, Luna 1);
  t06: Haiku low/high answered 5 (stay on the 2/3).
- **Ignoring the accessibility constraint** — t07: Haiku low/high chose 1 → S → 7; t08: Haiku answered F → 7,
  D → 1 → S and D → E → 6 at low/medium/high, all transferring at stations without the symbol.
- **Answering from normal service** — t10: Haiku medium/high used the 6, which is suspended between 28 St and
  Bleecker St.
- **Wrong transfer point** — t09: Chambers St instead of Canal St (Haiku low/medium, Luna); t04: Haiku medium chose
  59 St-Columbus Circle.
- **Illegal transfer** — t03: Haiku low J → A → 1 (no free transfer from the A to the 1 on this map).

### Failure analysis of the first two rounds

We sorted every wrong answer on a valid pilot task (13 in all: 5 Haiku, 8 GPT-6 Luna). For each one we compared the model's answer with alternative answers computed by code: the answer under normal service, and the answer without the accessibility constraint.

| Failure type | Count | Examples |
|---|---|---|
| **Ignored a stated constraint.** The answer is exactly the code-computed answer for normal service or without the ♿ rule | 4 | p1_03 Haiku: `Times Sq-42 St`, the normal-service transfer, but the 7 is suspended. p2_04 GPT: `5` stops, the normal-service count (6 with the R suspended). p2_05 Haiku and p2_09 GPT: the route without the accessibility rule. |
| **Misread which service runs where** | 4 | p1_07 Haiku: `["7","4"]`, but the 4 never reaches Lexington Av/63 St (correct: `["7","Q"]`). p2_05 GPT: `C` instead of `A` on a shared track. p2_01 Haiku: `7` instead of the `S` shuttle. |
| **Answer not supported by the map at all** | 2 | p2_06 GPT: `Bergen St`, a Brooklyn station that is not on the map. p2_11 GPT: `["6"]`, a service that serves neither the origin nor the destination. |
| **Wrong transfer station or label** | 2 | p2_10 Haiku: `42 St-Port Authority Bus Terminal`, the label at the other end of the Times Sq complex. p1_03 GPT: `34 St-Herald Sq`. |
| **Stop count off** | 1 | p1_01 GPT: `5` instead of `4`. |

## Pilot results

| Round | Generator | Tasks | Haiku 5.5 (high) | GPT-6 Luna (high) | Change made because of it |
|---|---|---|---|---|---|
| Pilot 1 | subway-0.2.0 | 12 (`tasks/pilot1`) | 10/12 (83%) | 9/12 (75%) | Both models solved every `count_stops`; the adversarial reviewer found an ambiguous walk-transfer. → dropped `count_stops` from the mix, required transfers inside one named station, added the `accessible_route` type, weekend (Saturday) timetable, MTA-style markers |
| Pilot 2 | subway-0.2.0 | 11 evaluated of 12 (`tasks/pilot2`) | 8/11 (73%) | 5/11 (45%) | `accessible_route` hardest (1/3 each). Test audit found the planner did not follow the stated walking/arrival rules and the accessible memory trap compared against the wrong baseline → planner rewritten on (station, route, arrived-by-train) states, rules stated in every question, closed stations never used as endpoints, U-turn trips rejected, max 3 rides |
| Final | subway-0.3.0 | 10 (`tasks/final`) | 5/10 (50%) | 8/10 (80%) | Hand check accepted all 10; equivalent services on the same legs accepted (e.g. A or C from 59 St to 42 St) |

Reasoning-effort sweep on the final 10 (Claude Haiku 5.5, temperature 0): **low 4/10, medium 5/10, high 5/10**
(`results/final_haiku_low`, `results/final_haiku_medium`, `results/final`). Exact commands:
`scripts/haiku_effort_sweep.sh`; the effort is sent as `reasoning.effort` in `eval/openrouter.py` (`build_body`) and
recorded in each folder's `run_config.json`.

## Our Key findings

- Final accuracy at high reasoning: Haiku 5.5 5/10, GPT-6 Luna 8/10; all 40 replies in the reported runs complete
  (`finish_reason=stop`, no API errors). Cost of the reported run: $0.062.
- By question type (Haiku low / medium / high / Luna high): `accessible_route` 1/2/1/3 of 3, `reroute_lines`
  2/2/2/3 of 3, `transfer_station` 1/0/2/1 of 2, `min_stops` 0/1/0/1 of 2.
- Fewest-stops planning is the weakest skill: t05 is failed by every run, and only one Haiku run solves t06 (it
  needs a one-stop hop onto an express).
- Accessibility is the clearest model gap: Haiku fails 2 of 3 wheelchair routes at low and high effort by changing
  trains at stations without the symbol; Luna solves all 3.
- More reasoning helps Haiku only a little here (low 4, medium 5, high 5).
- Run-to-run variance: before the reported run, the same 10 tasks built on macOS (8 of 10 images byte-identical to
  the submitted ones, the other 2 differing only in marker layout) gave Haiku 6/10 and Luna 7/10. That run was
  discarded and everything re-run on the submitted Docker-built images, so the reported numbers come from one
  complete run on exactly the submitted files. Single-run scores therefore move by one or two tasks even at
  `temperature=0`, consistent with the providers ignoring that parameter. Pilot and candidate runs are kept in
  `results/pilot1`, `results/pilot2` and `results/cand_*`.
- Adversarial review (Claude Opus 5.5 solving each task blind, then auditing the reference): all 10 final tasks
  valid; during development it caught real bugs (an ambiguous walk-transfer, a closed station used as a destination,
  an unstated arrival rule), each fixed in the generator.

## Hand check

Every reported task was checked by a team member on a review page showing the map, the notice, the question, the
code-computed reference trip leg by leg, the reviewer's verdict and each model's reasoning. Verdict for all 10:
**reference trip correct, keep**.

| task_id | Type | Checked | Notes |
|---|---|---|---|
| t01 | accessible_route | Grand Central closed for 4/5/6; A → E → 6 traced on the map | C may replace A (59 St → 42 St), accepted. All runs correct |
| t02 | reroute_lines | R suspended Union St–Court St; 4 to Atlantic Av, Q to DeKalb Av | All runs correct |
| t03 | reroute_lines | 2/3 suspended Park Place–Wall St; J → R → 1 via Canal St and the Whitehall/South Ferry connector | Haiku low tried J → A → 1 (no free transfer from the A to the 1 here) |
| t04 | transfer_station | 7 suspended west of Grand Central; transfer at 34 St-Herald Sq | Haiku medium chose 59 St-Columbus Circle |
| t05 | min_stops | 7 suspended 5 Av–Hudson Yards; reference trip (3 stops) confirmed on the map | Every run wrong: Haiku 2, Luna 1 |
| t06 | min_stops | Nevins St closed; stop count recounted by hand: 3 to Borough Hall (1), 4 express to Atlantic Av (1), 2 to Grand Army Plaza (2) = 4 | Staying on the 2/3 is 5 (also stops at Hoyt St); Haiku low/high answered 5 |
| t07 | accessible_route | Times Sq closed for the 7; A → S → 7 with accessible transfers | C may replace A, accepted. Haiku low/high chose 1 → S → 7 |
| t08 | accessible_route | Herald Sq closed for N/Q/R; D → A → S | Reviewer note: A, C or E from 59 St downtown — C accepted (the E doesn't serve that leg on this map). Haiku failed at every effort; Luna correct |
| t09 | transfer_station | Fulton St closed for 4/5; transfer at Canal St | Haiku low/medium and Luna said Chambers St |
| t10 | reroute_lines | 6 suspended 28 St–Bleecker St; F → L | Haiku medium/high used the suspended 6 |

## Evaluation settings

- Models (OpenRouter): `anthropic/claude-haiku-5.5`, `openai/gpt-6-luna`. Reported run: both at `reasoning.effort=high`.
- `temperature=0` is sent on every call. OpenRouter's model list does not show `temperature` as a supported
  parameter for either model (checked 2026-11-14), so providers may ignore it; the value sent is recorded.
- Fixed `max_tokens=32000` (reasoning tokens count toward it). One call per model × task; no best-of selection.
- The image is sent as a base64 PNG data URL. `tasks/final` was built inside the Docker image, and the reported runs
  used exactly those files, so a judge's Docker rebuild reproduces the evaluated images byte for byte. (A macOS
  build gives identical questions and answers; two images differ slightly in marker layout because floating-point
  rounding differs across operating systems.)

### Prompt (`eval/prompt.py`)

```
{question}

Answer the question using the image. Think it through, then {format_instructions}
End your reply with a final line of the form:
FINAL ANSWER: <answer>
```

| answer_type | Format instruction |
|---|---|
| `integer` | give the answer as a single whole number (digits only, no units). |
| `label` | give the answer exactly as written on the map (just the name, nothing else). |
| `sequence` | give the answer as a JSON list of names exactly as written on the map, in order, e.g. ["A", "7"]. |

Every task's exact prompt is saved with its raw response (`results/<set>/raw/<model>/<task_id>.json`).

### Extraction and scoring

- **Extraction** (`eval/extract.py`): the last `FINAL ANSWER:` line (fallback: the last line); markdown, quotes and
  trailing periods stripped; sequences accept a JSON list, commas or arrows.
- **Scoring** (`eval/score.py`): `integer` exact; `label` after normalisation (case, punctuation, hyphen variants);
  `sequence` item by item, against the reference or any entry of the task's `accepted_answers`.

### Errors and retries

HTTP 429/5xx, timeouts and connection errors are retried with exponential backoff (up to 6 attempts). Any row with
an API error, an empty reply or `finish_reason` other than `stop` makes the run exit non-zero, so the reported run
must be re-run in full. The reported run has none.

### Outputs (`results/<set>/`)

`responses.csv` (the 10 required columns), `responses.jsonl` (same rows plus full replies and usage),
`run_config.json` (models, temperature, max_tokens, effort, prompt template, timestamps, cost), `summary.md`,
`raw/` (full API responses including reasoning text where returned).

## Run in Docker

Build the image (holds the whole pipeline and its dependencies):

```bash
docker build -t transport-factory .
```

Rebuild the 10 reported tasks from their seeds (identical images, questions and answers — the command compares
image hashes, questions and answers against `tasks/final` and prints the result), validate them, then evaluate both
models and score them. Choose the models with `--models`; the seeds are in `configs/final.json`:

```bash
docker run --rm -e OPENROUTER_API_KEY -v "$PWD/out:/app/out" transport-factory reproduce --spec configs/final.json --out out/final --compare tasks/final --models anthropic/claude-haiku-5.5,openai/gpt-6-luna
```

Build, check and score one fresh task. Choose the seed with `--seed`, the question type with `--question-type`
(`reroute_lines`, `accessible_route`, `transfer_station`, `min_stops`) and the model with `--models`:

```bash
docker run --rm -e OPENROUTER_API_KEY -v "$PWD/out:/app/out" transport-factory fresh --family subway --seed 12345 --level 3 --question-type reroute_lines --out out/fresh --models anthropic/claude-haiku-5.5
```

Outputs land in `./out/` on the host. The key is passed only at run time; no key or `.env` is copied into the image.

### Local runs and tests

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m factory build --spec configs/final.json --out out/check        # build + validate
.venv/bin/python -m validate.review --tasks tasks/final                            # adversarial review (ANTHROPIC_API_KEY)
.venv/bin/python -m pytest -q                                                      # 94 pass, 16 expected failures (documented)
```

## Data sources and references

- MTA GTFS static subway feed (`https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip`, feed of 2026-10-28) and the
  MTA Subway Stations dataset on data.ny.gov (`39hk-dx4f`): stops, service patterns, run times, complexes, accessibility.
- NYC Open Data Borough Boundaries (shoreline-clipped), `data/nyc_boroughs.geojson`, for land and water.
- Real examples each image is modelled on: the **MTA New York City Subway map (2026 edition)** — lettered stop
  markers on each line and transfer pills — and the **MTA's weekend planned-work notices / "The Weekender" maps**
  for the service-change overlay; the **April 2026 print map** for the `print` style. Our maps are generated from
  data with our own layout; no MTA artwork, logo or route bullets are reproduced (stop markers and route badges are
  rounded squares, and every map says "Schematic generated from public GTFS data. Not an official map.").

## Reused components

- Libraries: numpy, matplotlib, pillow, pytesseract (Tesseract OCR), requests, anthropic SDK, pytest.
- `tools/check_submission.py`: organizer-provided format checker.
- `eval/tests/` came from a teammate's parallel eval implementation (PR #1); 12 of its tests encode that
  implementation's conventions and are marked expected-failure with reasons in `eval/tests/conftest.py`.
- No pre-existing project code. Built with AI coding assistance (Claude Code).

## Manual interventions

- The 10 final tasks were picked from a candidate pool for variety of question type and area; seeds that duplicated
  another task's trip or answer were replaced by searching the next seeds (`configs/final.json` records the seeds).
- Hand check of all 10 on the review page; one note (t08: A/C/E equivalence) led to the general `accepted_answers` rule.
- Map styling was iterated by eye against the MTA reference maps (label placement, transfer rows, part-time markers).
- No task answer was edited by hand; every answer is computed by code.

## Limitations

- One diagram family (subway maps). The generator interface (`generator/base.py`) supports more.
- The schematic layout distorts geography; shorelines are warped to follow it and look rough in places.
- A few stations in the densest areas (Downtown Brooklyn) can have a marker sitting on another line; tasks touching
  them are rejected by the validator rather than fixed in the renderer.
- Part-time stops are inferred from trip counts (< 85% of both neighbours) and maps showing them are excluded.
- `tasks/pilot1` and `tasks/pilot2` were rebuilt after their runs as the generator changed; `results/pilot1` and
  `results/pilot2` reflect the builds that were evaluated (each raw response stores the exact prompt sent).
- Service patterns are a typical Saturday daytime pattern from the October 2026 feed, not a specific date.
- `temperature=0` may be ignored by the providers (see above); results are single runs.
- Equivalent-service acceptance treats services stopping at both stations of a leg as equivalent even when one is
  local (more stops); the question states this rule.

## Team contributions

| Member | Contribution |
|---|---|
| TODO (name) | Pipeline design, subway map renderer and task generator, validation, hand check of all 10 tasks |
| Teammate (PR #1) | Evaluation module and tests (`eval/tests/`), README project structure and pilot failure analysis |
| TODO | Fill in the other team members |
