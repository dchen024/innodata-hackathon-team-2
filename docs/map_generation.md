# How the subway maps are generated

Every map image is drawn by code from public data. Nothing is traced from a published map and no image is
edited by hand. This document walks through the pipeline from the raw MTA files to the final PNG.

```
MTA GTFS feed + data.ny.gov station list
        │  build_graph.py
        ▼
data/subway_graph.json, data/subway_graph_saturday.json      (network graph)
        │  family.py: seed → map window + weekend service change
        ▼
render.py: pick stations ─► layout.py: schematic layout ─► matplotlib drawing ─► PNG + layout/audit report
```

| Stage | File | Main entry point |
|---|---|---|
| 1. Network graph | `generator/families/subway/build_graph.py` | `build(service, out)` |
| 2. Scenario | `generator/families/subway/family.py` | `SubwayFamily.generate(seed, level, question_type, style)` |
| 3. Layout | `generator/families/subway/layout.py` | `octilinear_relax`, `octi_path`, `offset_polyline`, `idw_warp` |
| 4. Drawing and audit | `generator/families/subway/render.py` | `render_map(graph, png_path, region, style, service_change=...)` |

Libraries: **numpy** for all geometry and **matplotlib** (headless Agg backend) for drawing. No mapping or
graph-drawing library is used.

---

## 1. Building the network graph

`build_graph.py` turns two public files into a JSON graph of the subway.

**Inputs** (downloaded by `fetch()` into `data/raw/`, which is not committed):

| File | URL | Used for |
|---|---|---|
| GTFS static subway feed | `https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip` | Routes, stations, timetable, transfers |
| MTA Subway Stations | `https://data.ny.gov/resource/39hk-dx4f.csv` | Complex IDs, borough, structure, wheelchair access |

**Steps**

1. **Routes** come from `routes.txt`: name, colour, text colour, and whether it is an express (its long name
   contains "Express"). Rush-hour express variants and the Staten Island Railway (`FX`, `6X`, `7X`, `SI`) are
   skipped.
2. **Stations** are the parent stations in `stops.txt` (`location_type == 1`). Each platform is mapped to
   its parent station. The data.ny.gov list adds `complex_id`, `borough`, `structure`, `ada`
   (1 = fully accessible, 2 = partially, 0 = not) and `daytime_routes`.
3. **Trips** are filtered to one service day (`Weekday` or `Saturday`). Only trips that start between
   07:00 and 19:00 are counted.
4. **Ride edges.** Each trip is read stop by stop from `stop_times.txt`. Every pair of consecutive stops
   becomes an edge for that route, keyed by the sorted station pair. Each edge stores:
   - `minutes`: the median time from departing one stop to arriving at the next;
   - `km`: the straight-line (haversine) distance;
   - `trips`: how many trips run over it.

   An edge is dropped if it appears in fewer than 10% of the route's trips (`MIN_SHARE`). This removes rare
   reroutes.
5. **Transfers** come from `transfers.txt`. Only links between two different stations that both have
   service are kept, using `min_transfer_time` (180 s if missing).
6. **Stop trips.** For each route and station, the number of trips that stop there is saved. The renderer
   uses it to find part-time stops.

**Output**

```json
{
  "source":     {"gtfs": "...", "stations": "...", "feed_version": "...", "feed_start": "...", "feed_end": "...", "service": "..."},
  "routes":     {"A": {"name": "A", "long_name": "...", "color": "#0062CF", "text_color": "#FFFFFF", "express": true}},
  "stations":   {"101": {"name": "Van Cortlandt Park-242 St", "lat": 40.889, "lon": -73.899, "complex_id": "293",
                         "borough": "Bx", "structure": "Elevated", "ada": 0, "daytime_routes": ["1"], "routes": ["1"]}},
  "ride_edges": [{"route": "1", "a": "101", "b": "103", "minutes": 1.5, "km": 0.54, "trips": 274}],
  "transfers":  [{"a": "112", "b": "A09", "minutes": 3.0}],
  "stop_trips": {"1": {"101": 274}}
}
```

Two graphs are written. Every task uses the Saturday one.

| File | Service | Routes | Stations | Ride edges | Transfers |
|---|---|---|---|---|---|
| `data/subway_graph.json` | Weekday | 25 | 475 | 714 | 75 |
| `data/subway_graph_saturday.json` | Saturday | 22 (no B, W, Z) | 475 | 603 | 75 |

```bash
python -m generator.families.subway.build_graph
```

---

## 2. Choosing what to draw

### Map windows

A map shows one rectangular window of the city, given as latitude/longitude bounds plus a rotation.

- **Task maps** use the 9 windows in `WINDOWS` in `family.py`: `times_sq`, `grand_central`, `union_sq`,
  `fulton`, `downtown_bk`, `lic`, `uws`, `jackson_hts` and `bway_jct`. `window_region()` turns each into a
  region at 250 pt per km.
- **Stand-alone maps** use `REGIONS` in `render.py` (`midtown`, `lower_manhattan_downtown_brooklyn`,
  `full_system`, and others).

Manhattan windows are rotated 29° so the street grid runs straight up and down, as on the official map.

### Stations included

`render_map` picks three sets of stations:

1. Stations inside the window plus a 60% margin on each side. These are laid out so the shape near the edges
   is right.
2. One more stop beyond that on every line, so lines leave the map in the right direction even when the next
   stop is far away.
3. After layout, the stations that fall inside the drawn frame. These are **"on the map"**: they get markers
   and a label, and they are returned as `stations_in_view`.

`family.visible_stations()` renders a probe map for a window once and caches its `stations_in_view`. The trip
planner only uses those stations, so no answer depends on a station the reader cannot see.

### Weekend service change

`SubwayFamily._scenario()` uses the task's seed to pick one of two kinds of change:

- **`suspend`**: pick a route with at least 3 edges on the map, then a stretch of 2–5 consecutive stops on it.
  Every route that runs over the same stretch (for example the 2 and the 3) is suspended with it. The notice
  reads "No 2 or 3 trains between X and Y, in both directions."
- **`skip`**: the station after the start of the stretch is closed and every route there runs through without
  stopping. The notice reads "X is closed: 4 5 6 trains run through without stopping, in both directions."

The change is passed to `render_map` as a dictionary:

```python
{"kind": "suspend", "routes": ["2", "3"], "from": "<stop_id>", "to": "<stop_id>", "notice": [...]}
{"kind": "skip", "station": "<stop_id>", "routes": ["4", "5", "6"], "notice": [...]}
```

---

## 3. Laying out the schematic (`layout.py`)

The layout keeps the real geography roughly in place but straightens every line to multiples of 45°.

### 3.1 Projection and rotation

`project()` converts latitude/longitude to a flat km grid centred on the window:

```
x = (lon − lon0) · cos(lat0) · 111.32
y = (lat − lat0) · 110.57
```

`rotate()` then turns the grid by the window's rotation. The result (`geo`) is both the starting layout and
the "true" position each station is pulled back toward.

### 3.2 Which station pairs get drawn

Before relaxing, `render_map` works out:

- **`draw_pairs`**: every pair of stations a line is drawn between, and which routes run along it.
  `_express_paths()` reroutes an express edge (for example 14 St → 34 St on the 2/3) through the local
  stations it passes, by searching the track of the same colour. The detour is accepted only if it has 3–8
  stations and is at most 1.3× the direct distance. This way express and local lines share one corridor.
  Stations an express passes through are recorded in `passes` and get no marker for it.
- **Complex links (`tlinks`)**: stations in the same complex are grouped by MTA `complex_id` or a GTFS
  transfer (`complex_groups()`, using union-find). Each group is joined by a minimum spanning tree (the
  shortest set of links that connects them all).

### 3.3 Relaxation (`octilinear_relax`)

600 iterations. The step size shrinks from 0.55 to 0.05 over the run. Each iteration applies these forces:

| Force | What it does |
|---|---|
| **Angle snap** | Each track link is rounded to the nearest multiple of 45°, with a length of at least `min_sep`. Both ends move halfway toward that target. |
| **Complex pull** | Stations in one complex are pulled to a target distance based on how many chips they carry, so their marker rows just touch. Their vertical gap is also reduced so they sit side by side. |
| **Spacing** | Any two stations closer than `min_sep` (0.36 km in renders) are pushed apart. Stations in one complex are exempt. |
| **Track clearance** | From 20% of the way in, on every other iteration: a station within `0.62 · min_sep` of a track it does not serve is pushed off it, and the track is pushed the other way. Otherwise the line would look like it stops there. |
| **Anchor** | Every station moves 2% of the way back toward its true position, so the map keeps its geography. |

### 3.4 Clean-up after relaxing (`render.py`)

1. **One row per complex.** The stations of each complex are placed on a single horizontal row, side by side,
   each as wide as its row of chips.
2. **Push apart sideways.** Up to 40 passes: stations that share a row and overlap are pushed apart along x.
   A complex always moves as one block.
3. **Drop down.** Up to 30 passes: if two rows still collide, the eastern row moves just below the western
   one.

### 3.5 Drawing links at 45° (`octi_path`)

Each link from `a` to `b` is drawn as a straight leg, a 45° leg, then another straight leg. Lines therefore
always enter and leave a station straight, so the chips sit square across the bundle. Links that are already
straight or exactly diagonal are drawn as one segment.

### 3.6 Warping the land (`idw_warp`, `simplify`)

Borough outlines from `data/nyc_boroughs.geojson` are projected and rotated in the same way, then simplified
(Douglas-Peucker, 0.16 km tolerance). Each shoreline point is then moved by a weighted average of how far the
nearby stations moved (inverse-distance weighting, power 2). Land and lines stay consistent: a station on the
waterfront stays on the waterfront.

---

## 4. Drawing the map (`render_map` in `render.py`)

### 4.1 Canvas and scale

- **Fixed scale**: 235 pt per km by default, 250 for task windows, 185 for the full system. The image grows
  instead of the chips and labels shrinking.
- **Frame**: the stations on the map plus 0.45 km of padding.
- **Size**: at least 12.5 inches wide, to leave room for the title and legend. Saved at 150 dpi.
- **Header band**: 1.15 in, plus a yellow notice band when there is a service change.

Two styles are defined in `STYLES`:

| Style | Look | Font |
|---|---|---|
| `clean` | White land, light blue water, dark header | DejaVu Sans |
| `print` | Cream land, grey-blue water | DejaVu Serif |

### 4.2 Drawing order

| Layer | What is drawn | How |
|---|---|---|
| 0 | Water | Rectangle |
| 0.5 | Land | Warped borough `Polygon`s |
| 0.8 | Borough names | Large pale text at the middle of each visible borough |
| 2 | Route lines | Parallel lanes (see 4.3) |
| 2.5–2.6 | Suspended stretches | White underlay plus a pale dashed lane |
| 5.9 | Complex connectors | Thin black lines between differently named parts of a complex |
| 6–6.6 | Stations | Pills, bars and chips (see 4.4) |
| 9–10 | Route badges | Rounded squares where routes leave the map or end |
| 12 | Labels | Station names with a halo, plus the accessibility symbol |

### 4.3 Route lines

1. **Lane order.** On each drawn pair, routes are sorted in a fixed order and placed at offsets of
   `(i − (n − 1) / 2) · gap`.
2. **Consistent sides.** A breadth-first pass over connected pairs flips the offset sign where needed, so a
   route stays on the same side of the bundle along a corridor.
3. **Continuous strokes.** Each route's pairs are joined into chains. Consecutive pairs with the same offset
   are merged into one polyline, then shifted sideways with mitred corners (`offset_polyline`). Each chain is
   drawn as one matplotlib line with round caps and joins.
4. **Lane positions.** The shifted point at each station is saved in `lane_xy[station][route]`. That is where
   the chip for that route goes.

### 4.4 Service change on the drawing

- **`suspend`**: a breadth-first search along the route finds the stops from `from` to `to`, including any
  express detours. Those lanes are drawn pale and dashed. The route loses its chip at every stop in between.
  It also loses its chip at an end of the stretch if it has no other service there.
- **`skip`**: the closed station loses the chips of every listed route.
- A station where no train stops any more is drawn as a white circle with a red **×**.

### 4.5 Station markers

- **Chips.** Each route that stops gets a black rounded-square chip with the route letter. A route that
  passes without stopping gets no chip, so the bare line reads as "express, doesn't stop".
- **Transfer stations.** Stations served by two or more line colours, or that are part of a transfer, get a
  white pill with a black outline around their chips. The pill is the convex hull of the chips (`_hull`), or
  a capsule when the chips are in a line.
- **Complexes.**
  - Platforms with the same name share one pill.
  - Differently named parts (for example Times Sq and Port Authority) each get their own pill, joined by thin
    black connectors drawn edge to edge.
- **Part-time stops.** A route's chip is hollow (white with a black letter) when that route stops at the
  station on fewer than 85% of the trips that stop at both neighbouring stations.
- **Tidy rows.** Chips that would overlap where lines meet from different directions are lined up in a neat
  row.

### 4.6 Route badges

- **Edges.** Where a drawn pair crosses the frame, a coloured badge for each route on it is placed 86% of the
  way to the edge.
- **Terminals.** Routes that end at a station on the map get a badge below that station.
- **Clearance.** Badges are nudged away from markers until they clear them.

### 4.7 Station labels

Labels are placed one at a time: transfer stations first, then in alphabetical order. A complex gets one label
per station name, using the name of its busiest station (`complex_head`).

1. **Candidates.** 8 positions around the station's own chips (right, left, above, below, and the four
   diagonals), at 3 distances (1.0×, 1.6× and 2.4× the base gap): 24 candidates.
2. **Measuring.** Each candidate is drawn and measured in real pixels with `get_window_extent`.
   matplotlib's `fig.canvas.draw()` is called first, so the measurements match the saved image.
3. **Rejected outright** if it leaves the frame or overlaps a badge, a pill or another station's markers.
4. **Cost** of the rest:
   - the number of 4-px grid cells of line it covers;
   - +3,000 for the middle distance and +10,000 for the far distance;
   - +40,000 if the label is closer to another station's markers than to its own, since a reader could take it
     for the wrong station.
5. The cheapest candidate wins. The search stops early at cost 0.
6. Fully accessible stations (`ada == 1`) get a blue **♿** symbol after the name.

### 4.8 Header, legend and footer

- **Title**: "Subway — \<window title\>", sized so it never runs under the legend.
- **Subtitle**: "Weekend service, Saturday and Sunday" or "Weekday daytime service".
- **Legend** (`_legend`), our own design. It explains:
  - a chip means the service stops; no chip means it passes (express);
  - an outlined chip means a transfer within the station;
  - joined pills mean a free transfer between stations;
  - a hollow chip means a part-time stop;
  - a badge means the route continues beyond the map or ends.
- **Notice band**: yellow, with "WEEKEND SERVICE CHANGE" and the notice lines.
- **Footer**: "Schematic generated from public GTFS data. Not an official map."

---

## 5. What `render_map` returns

After saving the PNG, `render_map` checks the result in pixels and returns a dictionary. `generator/build.py`
saves it as `layout` in `tasks/<set>/data/<id>.json`, and the checks in `validate/` read it.

| Key | Contents |
|---|---|
| `stations_in_view` | Stations on the map (the planner's station set) |
| `stations` | Per station: kind (`local`, `express`, `transfer`, `no_service`), routes that stop, routes that pass |
| `labels` | Per station: printed text, services, pixel box, how much line it covers, distance to its own and other markers, ambiguous flag, accessibility |
| `unlabelled` | Stations on the map that got no label (should be empty) |
| `badges`, `part_time`, `positions_km` | Badge positions, hollow chips, final layout in km |
| `no_stop`, `suspended` | Where the service change removed chips or greyed out lanes |
| `overlaps` | Problems found by the pixel audit (below) |

The audit reports:

- **marker/marker**: chips of different stations overlapping;
- **label/marker** and **label/label**: labels overlapping chips or each other;
- **marker/foreign-line**: a chip sitting on a line of a route that does not stop there, which would read as
  a false stop;
- **label/closer-to-other-station**: a label that could be read as belonging to a different station.

---

## 6. Reproducibility

- **Seeded.** Each task is fully determined by its seed. `generate()` uses
  `np.random.default_rng(seed)`, and every set and dictionary is iterated in sorted order.
- **Fixed environment.** Versions are pinned in `requirements.txt` (numpy 2.5.4, matplotlib 3.11.2). The
  `Dockerfile` installs `fonts-dejavu-core` so rebuilt images are byte-identical.
- **Checked.** `tasks.jsonl` stores each image's SHA-256 hash. `factory reproduce` rebuilds a set from its
  seeds and compares it with the submitted one.

---

## 7. Commands

```bash
# 1. Rebuild the network graphs from the MTA feed
python -m generator.families.subway.build_graph

# 2. Render a stand-alone map: output path, region from REGIONS, style (--minutes adds running times)
python -m generator.families.subway.render out.png midtown clean
python -m generator.families.subway.render full.png full_system clean

# 3. Build and validate a task set from a spec
python -m factory build --spec configs/final.json --out tasks/final

# 4. Build, check and (optionally) score one new task
python -m factory fresh --seed 12056 --question-type accessible_route --style clean --out tasks/fresh --no-eval
```

From Python:

```python
from generator.families.subway.render import load_graph, render_map

g = load_graph("saturday")
report = render_map(
    g, "map.png", region="midtown", style="clean",
    service_change={"kind": "skip", "station": "631", "routes": ["4", "5", "6"],
                    "notice": ["Grand Central-42 St is closed: 4 5 6 trains run through without stopping."]},
)
print(len(report["stations_in_view"]), report["overlaps"])
```

See `docs/maps/nyc_subway_full_system.pdf` for the whole system rendered by the same code.
