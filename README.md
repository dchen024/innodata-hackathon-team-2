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
| `generator/` | `base.py` family interface; `families/<name>.py` one module per diagram type |
| `validate/` | task-record checks and per-family render/answer checks |
| `eval/` | OpenRouter client, prompt, answer extraction, scoring, runner; tests in `eval/tests/` |
| `factory/` | command line: `build`, `validate`, `eval`, `reproduce`, `fresh` |
| `configs/` | task specs (family, seed, level, question type, style) for pilot and final sets |
| `tasks/<set>/` | `tasks.jsonl`, `images/`, `data/` (per-task JSON), `checks.json` |
| `results/<set>/` | `responses.csv`, `run_config.json`, `raw/` |
| `tools/` | organizer-provided `check_submission.py` |

## How the tasks were made hard and why the models failed

TODO after the pilot.

## Pilot results

| Round | Generator version | Tasks | Haiku 5.5 | GPT-6 Luna | Change made afterwards |
|---|---|---|---|---|---|
| 1 | TODO | | | | |

## Key findings

TODO.

## Hand check

One note per reported task: what was checked by eye against the data, and why it stumped the models.

| task_id | Checked | Notes |
|---|---|---|
| TODO | | |

## Evaluation settings

- Models (OpenRouter): `anthropic/claude-haiku-5.5`, `openai/gpt-6-luna`
- `temperature=0` is sent, but OpenRouter's model list does not show `temperature` as a supported parameter for either model (checked 2026-11-14), so providers may ignore it.
- `reasoning.effort=high`, fixed `max_tokens=32000` (see `results/final/run_config.json`). Reasoning tokens count toward `max_tokens`.
- One call per model × task. The image is sent as a base64 PNG data URL together with the prompt.

### Prompt

`eval/prompt.py` builds each prompt from the task's question, the options (multiple choice only, listed as `A. …`, `B. …`), a format line for the answer type and the answer instruction:

| answer_type | Format line |
|---|---|
| `number` | Give the answer as a plain number, without units. Plus, when the task has a tolerance: "Your answer counts as correct if it is within ±5% (or ±0.5) of the true value." |
| `integer` | Give the answer as a whole number, without units. |
| `label` | Give the answer exactly as it is written in the image. |
| `multiple_choice` | Give only the letter of the correct option. |
| `sequence` | Give the items in order, separated by commas, each written exactly as in the image. |

Every prompt ends with: *"Answer the question about the image. Think it through, then end your reply with a final line of the form `FINAL ANSWER: <answer>`"*. The template and every task's exact prompt are saved in `run_config.json` (`prompt_template`, `task_prompts`).

### Answer extraction and scoring

- **Extraction** (`eval/extract.py`): only the last `FINAL ANSWER:` line counts. Markdown, `$…$`, `\boxed{}`, quotes and trailing periods are stripped. Numbers accept thousands separators, units and the minus sign `−`. Letters accept `B`, `(B)`, `b.` and `Option B`. Sequences accept commas, `;`, `->`, `→` or a JSON list. If no answer can be read, `parsed` is empty and the row scores 0; that is not an API error.
- **Scoring** (`eval/score.py`):
  - `number`: within `tolerance_rel` (fraction of the true value) or `tolerance_abs`.
  - `integer`: exact.
  - `label`: compared after the same normalisation the organizers' checker uses (lower case, punctuation and a leading "the" dropped).
  - `multiple_choice`: same letter.
  - `sequence`: same length, and every item matches in order.

### Errors and retries

- **Retried:** HTTP 429, 408 and 5xx responses, timeouts, connection errors, and replies with an error or empty content. Waits back off exponentially, honouring `Retry-After`, for up to 6 attempts per call. Cost is summed over all attempts.
- **Not retried:**
  - HTTP 400, 401, 402, 403 and 404 responses (`error=api_error`).
  - Replies cut off at `max_tokens` (`finish_reason=length`, `error=length`).
- Rows with an error have an empty `correct`. Every retry and failure is logged in `results/<set>/errors.jsonl`.

### Outputs (`results/<set>/`)

| File | Contents |
|---|---|
| `responses.csv` | One row per model × task: `model, task_id, status, parsed, question_type, response, ref_answer, correct, finish_reason, error` |
| `run_config.json` | Models, temperature, max_tokens, reasoning effort, prompt template, each task's prompt, timestamps, cost per model and total, accuracy summary |
| `raw/<provider>__<model>/<task_id>.json` | The full API response, including the model's reasoning text where the provider returns it, plus usage and the attempt log |
| `errors.jsonl` | Calls that needed a retry or failed |

Tasks listed under `failed` in `tasks/<set>/checks.json` are skipped. A rerun reuses every `raw/` file whose call succeeded with the same prompt and settings, so only missing or failed calls are paid for again.

### Run the evaluation locally

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
cp .env.example .env          # then fill in OPENROUTER_API_KEY (.env is gitignored)
.venv/bin/python -m factory eval --tasks tasks/pilot1 --out results/pilot1 [--max-tokens 32000] [--effort high] [--workers 4]
.venv/bin/python -m pytest eval/tests     # unit tests + an end-to-end run with the API faked
```

The command prints accuracy and cost per model. If any reply has `api_error` or `length`, it prints a warning: the submission check requires every response to be complete. Raise `--max-tokens` for `length` and rerun.

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
docker run --rm -e OPENROUTER_API_KEY -v "$PWD/out:/app/out" transport-factory fresh --family TODO --seed 12345 --out out/fresh --models anthropic/claude-haiku-5.5
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
