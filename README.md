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
| `eval/` | OpenRouter client, prompt, answer extraction, scoring, report |
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
- `reasoning.effort=high`, fixed `max_tokens` (see `results/final/run_config.json`).

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
- TODO: libraries and any pre-existing code.

## Manual interventions

TODO.

## Limitations

TODO.

## Team contributions

| Member | Contribution |
|---|---|
| TODO | |
