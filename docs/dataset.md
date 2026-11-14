# Dataset

The dataset has two layers:

1. **Source data** (`data/`): the NYC subway network built from public MTA data.
2. **Tasks** (`tasks/`): rendered map images, each with a trip-planning question and an answer computed by
   code.

How the maps are drawn is covered in [`map_generation.md`](map_generation.md).

---

## 1. Source data (`data/`)

| File | Source | Contents |
|---|---|---|
| `subway_graph.json` | MTA GTFS feed + data.ny.gov station list | Weekday network: 25 routes, 475 stations, 714 ride edges, 75 transfers |
| `subway_graph_saturday.json` | Same, Saturday timetable | Weekend network: 22 routes (no B, W, Z), 475 stations, 603 ride edges, 75 transfers. **Used by every task.** |
| `nyc_boroughs.geojson` | NYC Open Data borough boundaries | Shorelines of the 5 boroughs (land and water) |

- **Feed:** `20261028-fall-2026-pick-with-long-term-supplements`, valid 2026-11-01 to 2027-05-15.
- **Time window:** only trips starting between 07:00 and 19:00 are counted.

Each graph contains:

- **`routes`**: name, colour, text colour, express flag.
- **`stations`**: name, latitude/longitude, `complex_id`, borough, structure, `ada` (1 = fully accessible,
  2 = partially, 0 = not), routes stopping there.
- **`ride_edges`**: one record per pair of consecutive stops on a route, with the median running time in
  minutes, distance in km, and trip count.
- **`transfers`**: walking links between stations of one complex.
- **`stop_trips`**: trips per route per station, used to detect part-time stops.

Rebuild with `python -m generator.families.subway.build_graph`. The raw downloads go to `data/raw/`, which
is not committed.

---

## 2. Task sets (`tasks/`)

Each set is built from a spec in `configs/`. Every spec entry gives a seed, a difficulty level, a question
type and a map style, and the same seed always produces the same task.

| Set | Spec | Tasks | Purpose |
|---|---|---|---|
| `pilot1` | `configs/pilot.json` | 12 | First difficulty pilot |
| `pilot2` | `configs/pilot2.json` | 12 | Second difficulty pilot |
| `candidates` | `configs/candidates.json` | 10 | Candidates for the final set |
| `cand_pool` | `configs/cand_pool.json` | 20 | Larger candidate pool |
| **`final`** | **`configs/final.json`** | **10** | **Reported tasks** |

### Folder layout

```
tasks/<set>/
├── tasks.jsonl      one record per task
├── images/tNN.png   the rendered map
├── data/tNN.json    full scenario and render layout
├── checks.json      automated validation results
└── review.json      AI reviewer (Claude Opus 5.5) results
```

### Task record (`tasks.jsonl`)

| Field | Meaning |
|---|---|
| `task_id`, `image`, `data` | ID and relative paths to the image and scenario file |
| `question` | Full question text; it states the trip rules |
| `answer`, `answer_type` | Reference answer; `sequence` (JSON list), `label` (station name) or `integer` |
| `accepted_answers` | Other correct answers, where another service runs between the same two stations on a leg |
| `question_type` | `reroute_lines`, `accessible_route`, `transfer_station` or `min_stops` |
| `family`, `level`, `style`, `seed`, `generator_version` | How to rebuild the task |
| `image_sha256` | Hash of the PNG, used to confirm a rebuild is identical |
| `references` | Real-world maps the image is modelled on |
| `checks`, `valid` | Result of each validation check, and whether all passed |

### Scenario file (`data/tNN.json`)

- **`window` and `region`**: which part of the city is shown.
- **`service_change`**: the weekend change: `suspend` (no service on a stretch) or `skip` (station closed),
  with the notice text.
- **`question_meta`**: origin, destination, the trips worked out by code, the answer under normal service
  (`normal_answer`), and the accepted answers.
- **`stations_in_view`**: the stations drawn on the map. The answer is computed using only these.
- **`layout`**: the renderer's report: positions, labels, chips per station, and the overlap audit.

---

## 3. Question types

| Type | What the model must do | Answer |
|---|---|---|
| `reroute_lines` | Fewest transfers, then fewest stops, from A to B under the change; list the services ridden | `sequence` |
| `accessible_route` | Same, but only entering, leaving or changing at stations with the ♿ symbol | `sequence` |
| `transfer_station` | Name the single station where the best one-transfer trip changes trains | `label` |
| `min_stops` | Fewest station stops from A to B (transfers allowed, free) | `integer` |

Every question states the rules: walking between joined stations counts as a transfer, and the trip ends when
a train arrives at the destination itself.

---

## 4. The final set (`tasks/final`)

All 10 tasks are level 3 and use the Saturday network.

| Task | Window | Style | Type | Weekend change | Answer | Normal-service answer |
|---|---|---|---|---|---|---|
| t01 | Midtown West | clean | accessible_route | Grand Central-42 St closed (4 5 6) | A → E → 6 (or C → E → 6) | A → S → 6 |
| t02 | Downtown Brooklyn | clean | reroute_lines | No R, Union St – Court St | 4 → Q | R |
| t03 | Lower Manhattan | clean | reroute_lines | No 2/3, Park Place – Wall St | J → R → 1 | J → 2/3 → 1 |
| t04 | Midtown East | print | transfer_station | No 7, Grand Central – 34 St-Hudson Yards | 34 St-Herald Sq | 42 St-Bryant Pk |
| t05 | Midtown West | clean | min_stops | No 7, 5 Av – 34 St-Hudson Yards | 3 | 2 |
| t06 | Downtown Brooklyn | print | min_stops | Nevins St closed (2 3 4) | 4 | 5 |
| t07 | Midtown East | print | accessible_route | Times Sq-42 St closed (7) | A → S → 7 (or C → S → 7) | A → 7 |
| t08 | Midtown West | clean | accessible_route | 34 St-Herald Sq closed (N Q R) | D → A → S (or D → C → S) | N/Q/R → S |
| t09 | Lower Manhattan | print | transfer_station | Fulton St closed (4 5) | Canal St | no one-transfer trip |
| t10 | Union Square & Chelsea | print | reroute_lines | No 6, 28 St – Bleecker St | F → L | 6 → L |

The weekend answer is never the same as the normal-service answer. A model that answers from memory of the
real subway, or ignores the notice, gets it wrong.

### Validation checks

Every task in `final` passes all 12 checks in its `checks` field:

| Check | What it confirms |
|---|---|
| `schema` | Record has the required fields and formats |
| `answer_recomputed` | An independent search reaches the same answer as the generator |
| `render_matches_data` | Chips on the map match the services that stop there after the change |
| `names_visible` | Every station named in the question or answer is labelled with that exact text |
| `ocr_names` | Tesseract OCR can read those names in the PNG |
| `markers_clear_of_other_lines` | No station used by the task has a chip sitting on a line that doesn't stop there |
| `no_part_time_stops` | The map has no part-time (hollow) stops, which would make trip answers debatable |
| `accepted_answers_valid` | Every accepted alternative is a real trip on this map with the minimum number of transfers, and the reference answer is among them |
| `labels_unambiguous` | No station named in the task has a label closer to another station than to its own |
| `unique_answer` | The independent recomputation agrees on a single answer (automatic for `min_stops`, since a minimum count is unique) |
| `memory_trap` | The normal-service answer is different |
| `chip_legibility` | Chip letters stay at least 9 px after downscaling to a 1568 px long side, the typical model API resize |

### Results (`results/final/summary.md`)

| Model | Correct |
|---|---|
| Claude Haiku 5.5 | 5/10 |
| GPT-6 Luna | 8/10 |

t05 (`min_stops`, answer 3) is answered wrongly by every model run.

---

## 5. Rebuilding

```bash
python -m generator.families.subway.build_graph                            # source graphs
python -m factory build --spec configs/final.json --out tasks/final         # build + validate a set
python -m factory reproduce --spec configs/final.json --out /tmp/repro --no-eval   # rebuild and compare
```
