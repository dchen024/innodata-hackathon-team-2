# Transportation Visual Task Factory — Innodata Hackathon, Track 2

> TODO (team): one-paragraph summary once the diagram families are chosen.

## Reported folders

- Tasks: `tasks/final`
- Results: `results/final`

## Problem statement

TODO: which transportation visuals (e.g. transit maps, timetables, route diagrams), and why reading them correctly matters.

## How the pipeline works

```
seed + spec ─► generator (structured data JSON) ─► renderer (PNG) ─► question + answer computed from data
            ─► validate/ (re-compute answer, OCR/pixel render checks, legibility, uniqueness)
            ─► eval/ (OpenRouter calls, answer extraction, scoring, report)
```

| Folder | Contents |
|---|---|
| `generator/` | `base.py` family interface; `families/subway/` builds the NYC subway graph from MTA GTFS data, lays it out, renders the map and generates the questions |
| `validate/` | task-record checks, independent answer recomputation, render and OCR checks, AI reviewer (`review.py`) |
| `eval/` | evaluates the models: OpenRouter client, prompt, answer extraction, scoring, runner; tests in `eval/tests/` |
| `factory/` | command line: `build`, `validate`, `eval`, `reproduce`, `fresh` |
| `configs/` | task specs (family, seed, level, question type, style) for the pilot and final sets |
| `data/` | subway graphs built from MTA GTFS (weekday and Saturday service) |
| `docs/maps/` | full-system map rendered by the generator (`nyc_subway_full_system.pdf`) |
| `tasks/<set>/` | `tasks.jsonl`, `images/`, `data/` (per-task JSON), `checks.json`, `review.json` |
| `results/<set>/` | `responses.csv`, `responses.jsonl`, `run_config.json`, `summary.md`, `raw/` |
| `tools/` | organizer-provided `check_submission.py` |

## Project structure

```
innodata-hackathon-team-2-1/
├── README.md
├── Dockerfile                    Python + Tesseract OCR + fixed fonts
├── requirements.txt
├── .env.example                  template for OPENROUTER_API_KEY (copy to .env, never committed)
│
├── configs/
│   ├── pilot.json                pilot 1 spec (12 tasks)
│   ├── pilot2.json               pilot 2 spec (12 tasks)
│   └── final.json                final spec (to fill in)
│
├── data/
│   ├── subway_graph.json         weekday service graph
│   └── subway_graph_saturday.json
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
├── tasks/pilot1/, pilot2/        built task sets
├── results/pilot1/, pilot2/      evaluation results
├── slides/                       presentation
└── tools/check_submission.py     organizers' format checker
```

How the pieces connect:

```
configs → generator → tasks/ → validate → eval → results/
          (draw + ask)          (check)    (test models)
```

## How the tasks were made hard and why the models failed

**What makes the tasks hard.** Each map shows a weekend **service change** (a notice strip, a pale dashed track and missing stop markers) or a station closure. The generator only keeps scenarios where the weekend answer **differs** from the normal-service answer, so a model that answers from memory of the real NYC subway, or misses the notice, gets it wrong. On top of that, the model has to read which services stop where (express services pass a station without a marker) and plan a trip with several legs. The `accessible_route` questions add one more constraint: the rider may only enter, leave or change trains at stations with the ♿ symbol.

**Why the models failed.** We sorted every wrong answer on a valid pilot task (13 in all: 5 Haiku, 8 GPT-6 Luna). For each one we compared the model's answer with alternative answers computed by code: the answer under normal service, and the answer without the accessibility constraint.

| Failure type | Count | Examples |
|---|---|---|
| **Ignored a stated constraint.** The answer is exactly the code-computed answer for normal service or without the ♿ rule | 4 | p1_03 Haiku: `Times Sq-42 St`, the normal-service transfer, but the 7 is suspended. p2_04 GPT: `5` stops, the normal-service count (6 with the R suspended). p2_05 Haiku and p2_09 GPT: the route without the accessibility rule. |
| **Misread which service runs where** | 4 | p1_07 Haiku: `["7","4"]`, but the 4 never reaches Lexington Av/63 St (correct: `["7","Q"]`). p2_05 GPT: `C` instead of `A` on a shared track. p2_01 Haiku: `7` instead of the `S` shuttle. |
| **Answer not supported by the map at all** | 2 | p2_06 GPT: `Bergen St`, a Brooklyn station that is not on the map. p2_11 GPT: `["6"]`, a service that serves neither the origin nor the destination. |
| **Wrong transfer station or label** | 2 | p2_10 Haiku: `42 St-Port Authority Bus Terminal`, the label at the other end of the Times Sq complex. p1_03 GPT: `34 St-Herald Sq`. |
| **Stop count off** | 1 | p1_01 GPT: `5` instead of `4`. |

## Pilot results

| Round | Generator version | Tasks | Haiku 5.5 | GPT-6 Luna | Change made afterwards |
|---|---|---|---|---|---|
| 1 | subway-0.2.0 | 12 (count_stops, min_stops, reroute_lines, transfer_station) | 10/12 (83%) | 9/12 (75%) | TODO |
| 2 | subway-0.2.0 | 11 evaluated (accessible_route, min_stops, reroute_lines, transfer_station) | 8/11 (73%) | 5/11 (45%) | TODO |

Both runs were clean (no API errors or cut-off replies). Total cost: $0.058 for pilot 1 and $0.071 for pilot 2. Per-task results are in `results/pilot1/summary.md` and `results/pilot2/summary.md`.

## Key findings

- **Accessibility and rerouting are the hardest question types.** In pilot 2, `accessible_route` was 1/3 for both models and `reroute_lines` was 0/2 for GPT-6 Luna. `count_stops` was 3/3 for both models in pilot 1, so it is the easiest type.
- **Constraints get dropped.** 4 of the 13 wrong answers match exactly what code computes when the service change or the accessibility rule is ignored. The models read the map but fall back to the "usual" trip.
- **GPT-6 Luna answers from memory of the real NYC subway.** Twice it named a station or service that cannot be right on the map shown (`Bergen St` is not on the map; the `6` serves neither end of the trip).
- **The two models fail differently.** Haiku 5.5 writes its reasoning (370–1,500 characters) and twice said the map was unclear (p1_07, p2_01). A hand check of p2_01 confirms it: the `F Q` marker for Lexington Av/63 St sits in the row of Lexington Av/59 St pills, and the "Lexington Av/63 St" label is printed away from it. The reference answer `["S","Q"]` is still correct (the S reaches Times Sq-42 St in 1 stop, the 7 in 2), but final tasks should avoid this label placement. GPT-6 Luna replies with only the final line (15–32 characters) and its reasoning is hidden, so its errors can only be classified by comparing with the code-computed alternatives.
- **Effort does not guarantee accuracy.** Reasoning used up to 13,934 tokens per call (p1_09, GPT-6 Luna, wrong). That is well under the 32,000-token limit, so no reply was cut off.
- **Plan for the final set:** favour `accessible_route`, `reroute_lines` and `transfer_station` at level 3, spread across map areas; drop `count_stops`.

## Hand check

One note per reported task: what was checked by eye against the data, and why it stumped the models.

| task_id | Checked | Notes |
|---|---|---|
| TODO | | |

## Evaluating the models

The agents under test are two vision-language models reached through OpenRouter. Each one gets a rendered subway map and a commuter question, and must reply with a single checkable answer. The evaluation code is in `eval/`.

### Settings

- Models (OpenRouter): `anthropic/claude-haiku-5.5`, `openai/gpt-6-luna`
- `temperature=0` is sent, but OpenRouter's model list does not show `temperature` as a supported parameter for either model (checked 2026-11-14), so providers may ignore it.
- `reasoning.effort=high`, fixed `max_tokens=32000` (see `results/<set>/run_config.json`). Reasoning tokens count toward `max_tokens`.
- One call per model × task, 6 calls in parallel. The user message holds the text prompt and the map as a base64 PNG data URL.

### Prompt

`eval/prompt.py` fills one template:

```
{question}

Answer the question using the image. Think it through, then {format_instructions}
End your reply with a final line of the form:
FINAL ANSWER: <answer>
```

| answer_type | `format_instructions` |
|---|---|
| `number` | give the answer as a single number (digits only, no units). |
| `integer` | give the answer as a single whole number (digits only, no units). |
| `label` | give the answer exactly as written on the map (just the name, nothing else). |
| `multiple_choice` | give the answer as the single letter of the correct option. If the question does not list the options, they are appended as `A) …`, `B) …`. |
| `sequence` | give the answer as a JSON list of names exactly as written on the map, in order, e.g. `["A", "7"]`. |

Tolerances are stated in the question text itself. The template and format lines are saved in `run_config.json`; the exact prompt of every call is in `raw/<model>/<task_id>.json` under `request.prompt`.

### Answer extraction and scoring

- **Extraction** (`eval/extract.py`): the answer is the text after the last `FINAL ANSWER:` in the reply. If the marker ends a line, the next line is used; if there is no marker, the last non-empty line. Markdown, `$…$` and `\boxed{}` are stripped.
  - Numbers accept thousands separators, units and Unicode minus signs.
  - Letters accept `B`, `(B)`, `B)` and `Option B`.
  - Sequences accept a JSON list, or items separated by commas, `;`, `->`, `→` or "then".
  - A reply with no readable answer scores 0. It is not an API error.
- **Scoring** (`eval/score.py`):
  - `number`: within the task's `tolerance_rel` or `tolerance_abs`.
  - `integer`: exact.
  - `label`: case-insensitive, with dashes, quotes and spaces unified, `St.` = `St`, `Ave.` = `Ave`, and a leading "the" ignored. So `Times Sq - 42 St` matches `Times Sq-42 St`.
  - `multiple_choice`: same letter.
  - `sequence`: same length, and every item matches in order under the label rules.

### Errors and retries

- **Retried, up to 6 attempts:** HTTP 408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524 and 529 responses, timeouts, connection errors, replies that are not JSON, and 200 replies that carry an error object or no choices. Waits back off exponentially, up to 60 s.
- **Not retried:** other HTTP errors such as 400, 401, 402 and 403.
- **Row values:**
  - A failed call is written as `status=api_error, error=api_error`.
  - A reply cut off at `max_tokens` is written as `status=ok, error=length`.
  - Rows with an error have an empty `correct`.
- **A reported run must be clean:** every row `ok`, with no error and `finish_reason=stop`. Otherwise the runner prints a "RUN NOT CLEAN" warning, adds it to `summary.md` and exits with code 1. Raise `--max-tokens` or fix the API error, then rerun all tasks.
- **Invalid tasks:** tasks with `"valid": false` in `tasks.jsonl` are skipped and listed in `run_config.json`. The reported `tasks.jsonl` must hold only accepted tasks.

### Outputs (`results/<set>/`)

| File | Contents |
|---|---|
| `responses.csv` | One row per model × task: `model, task_id, status, parsed, question_type, response, ref_answer, correct, finish_reason, error`. Replies longer than 100,000 characters are cut in the CSV only. |
| `responses.jsonl` | The same rows with the full reply, plus cost, usage, attempts and error detail |
| `summary.md` | Accuracy per model and per question type, the answer per task, and cost |
| `run_config.json` | Models, temperature, max_tokens, reasoning effort, prompt template, scoring rules, timestamps, accuracy, cost per model and total |
| `raw/<provider>__<model>/<task_id>.json` | The request (prompt and settings), the full API response including any reasoning text, parsed answer, score, usage, retry log and latency |

### Run the evaluation locally

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
cp .env.example .env          # then fill in OPENROUTER_API_KEY (.env is gitignored)
.venv/bin/python -m eval --tasks tasks/pilot2 --out results/pilot2 [--models a,b] [--max-tokens 32000] [--workers 6] [--effort high]
.venv/bin/python -m pytest eval/tests
```

`python -m factory eval --tasks … --out …` runs the same evaluation with the default settings. The tests use a faked API. 12 of them come from an earlier version of `eval/` and are marked as expected failures (`xfail`) where the conventions differ; `eval/tests/conftest.py` lists why.

## Run in Docker

```bash
docker build -t transport-factory .
```

Rebuild the 10 reported tasks from their seeds, then evaluate both models and score them:

```bash
docker run --rm -e OPENROUTER_API_KEY -v "$PWD/out:/app/out" transport-factory reproduce --spec configs/final.json --out out/final --models anthropic/claude-haiku-5.5,openai/gpt-6-luna
```

Build, check and score one fresh task (choose the seed with `--seed` and the model with `--models`):

```bash
docker run --rm -e OPENROUTER_API_KEY -v "$PWD/out:/app/out" transport-factory fresh --family subway --seed 12345 --out out/fresh --models anthropic/claude-haiku-5.5
```

## Reused components

- `tools/check_submission.py`: organizer-provided format checker.
- `requests` for the OpenRouter API calls. `pytest` for the tests (local only, not in the Docker image).
- TODO: other libraries and any pre-existing code.

## Manual interventions

TODO.

## Limitations

TODO.

## Team contribution 
| Member | Contribution |
|---|---|
| TODO | |
