"""Checks for subway tasks.

1. answer_recomputed   the reference answer recomputed with an independent search (0-1 BFS / leg enumeration),
                       not the generator's Dijkstra
2. render_matches_data every station's lettered chips in the rendered layout equal the services that stop there
                       in the network the answer was computed on (service change applied)
3. names_visible       every station named in the question/answer is labelled on the map with that exact text
4. ocr_names           tesseract finds those names in the PNG (legibility)
5. unique_answer       generator found exactly one optimal answer (stored meta) and recomputation agrees
6. memory_trap         (level>=2) the normal-service answer differs, so the image is required
7. chip_legibility     chip letters stay >= 9 px after the model APIs' typical downscale to 1568 px long side
"""
from __future__ import annotations

import json
import re
from collections import defaultdict, deque

from PIL import Image

from generator.families.subway.family import network
from generator.families.subway.render import load_graph

_G = None


def graph():
    global _G
    if _G is None:
        _G = load_graph("saturday")
    return _G


def _labels(data):
    return {s: v["text"] for s, v in data["layout"]["labels"].items()}


def _walk(g, in_view):
    """Free transfers (independent of the generator's code): stations sharing an MTA complex id, plus any
    GTFS transfer, closed transitively."""
    w = defaultdict(set)
    groups = {}
    for s in sorted(in_view):
        groups.setdefault(g["stations"][s]["complex_id"], set()).add(s)
    pairs = [(a, b) for G in groups.values() for a in G for b in G if a != b]
    pairs += [(t["a"], t["b"]) for t in g["transfers"] if t["a"] in in_view and t["b"] in in_view]
    for a, b in pairs:
        w[a].add(b)
        w[b].add(a)
    changed = True
    while changed:                                   # transitive closure
        changed = False
        for a in list(w):
            new = set().union(*(w[b] for b in w[a])) - {a}
            if not new <= w[a]:
                w[a] |= new
                changed = True
    return w


def min_stops_01bfs(g, in_view, sc, o, d):
    stops, ride = network(g, in_view, sc)
    nbr = defaultdict(set)
    for r, es in ride.items():
        for a, b in es:
            nbr[(a, r)].add((b, r))
            nbr[(b, r)].add((a, r))
    walk = _walk(g, in_view)
    dist = {}
    dq = deque()
    W_ = _walk(g, in_view)
    O = sorted({o} | W_[o])
    D = sorted({d} | W_[d])
    for o_ in O:
        for r in stops[o_]:
            dist[(o_, r)] = 0
            dq.append((o_, r))
    while dq:
        s, r = dq.popleft()
        k = dist[(s, r)]
        free = [(s, r2) for r2 in stops[s] if r2 != r] + [(s2, r2) for s2 in walk[s] for r2 in stops[s2]]
        for n in free:
            if dist.get(n, 1e9) > k:
                dist[n] = k
                dq.appendleft(n)
        for n in nbr[(s, r)]:
            if dist.get(n, 1e9) > k + 1:
                dist[n] = k + 1
                dq.append(n)
    vals = [dist[(d_, r)] for d_ in D for r in stops[d_] if (d_, r) in dist]
    return min(vals) if vals else None


def enumerate_trips(g, in_view, sc, o, d, max_legs=3, access=None):
    """All trips with <= max_legs legs: board a route, ride to a stop, transfer (same station or walk), ...
    Returns {(n_transfers, n_stops, (route names...), (transfer station ids...))}."""
    stops, ride = network(g, in_view, sc)
    walk = _walk(g, in_view)
    adj = defaultdict(lambda: defaultdict(set))
    for r, es in ride.items():
        for a, b in es:
            adj[r][a].add(b)
            adj[r][b].add(a)

    def reach(r, s):                                  # stops reachable on route r from s, with stop counts
        dist, q = {s: 0}, deque([s])
        while q:
            u = q.popleft()
            for v in adj[r][u]:
                if v not in dist:
                    dist[v] = dist[u] + 1
                    q.append(v)
        return dist

    out = set()
    R = g["routes"]
    D = {d} | walk[d]

    def go(s, legs, xfers, nst, used):
        if len(legs) >= max_legs:
            return
        for r in sorted(stops[s]):
            if r in used:
                continue
            for t, n in reach(r, s).items():
                if t == s:
                    continue
                L = legs + [R[r]["name"]]
                if t in D and (access is None or t in access):
                    out.add((len(L) - 1, nst + n, tuple(L), tuple(xfers)))
                if access is not None and t not in access:
                    continue
                for t2 in [t] + sorted(walk[t]):
                    if access is not None and t2 not in access:
                        continue
                    go(t2, L, xfers + [t], nst + n, used | {r})

    for o_ in sorted({o} | walk[o]):
        if access is None or o_ in access:
            go(o_, [], [], 0, frozenset())
    return out


def check(task: dict, data: dict, png_path: str) -> dict:
    g = graph()
    S = g["stations"]
    q = data["question"]
    meta = q["meta"]
    in_view = set(data["stations_in_view"])
    sc = data["service_change"]
    labels = _labels(data)
    res = {}

    # 1 independent recomputation
    qt = q["question_type"]
    try:
        if qt == "min_stops":
            v = min_stops_01bfs(g, in_view, sc, meta["origin"], meta["dest"])
            res["answer_recomputed"] = dict(passed=v == task["answer"], recomputed=v)
        elif qt in ("reroute_lines", "transfer_station", "accessible_route"):
            acc = None
            if qt == "accessible_route":
                # accessibility read from what the map PRINTS: stations whose label carries the symbol
                acc = {s_ for s_, v in data["layout"]["labels"].items() if v.get("accessible")}
            trips = enumerate_trips(g, in_view, sc, meta["origin"], meta["dest"], access=acc)
            if qt == "transfer_station":
                trips = {t for t in trips if t[0] == 1}
            best = min((t[0], t[1]) for t in trips) if trips else None
            opt = [t for t in trips if (t[0], t[1]) == best]
            if qt in ("reroute_lines", "accessible_route"):
                ans = sorted({t[2] for t in opt})
                ok = len(ans) == 1 and list(ans[0]) == task["answer"]
                res["answer_recomputed"] = dict(passed=ok, recomputed=[list(a) for a in ans])
            else:
                ans = sorted({labels.get(t[3][0], S[t[3][0]]["name"]) for t in opt})
                res["answer_recomputed"] = dict(passed=ans == [task["answer"]], recomputed=ans)
        elif qt == "count_stops":
            # count chips of the route along its line, read from the RENDERED layout
            r = meta["route"]
            lay = data["layout"]["stations"]
            path = meta["path"]
            mid = [s for s in path[1:-1] if r in lay.get(s, {}).get("stops", [])]
            res["answer_recomputed"] = dict(passed=len(mid) == task["answer"], recomputed=len(mid))
    except Exception as e:                            # never let a checker crash hide a problem
        res["answer_recomputed"] = dict(passed=False, error=repr(e))

    # 2 rendered chips == network stops
    stops, _ = network(g, in_view, sc)
    mism = []
    for s in sorted(in_view):
        drawn = set(data["layout"]["stations"].get(s, {}).get("stops", []))
        want = {r for r in stops[s]}
        if drawn != want:
            mism.append(dict(station=S[s]["name"], drawn=sorted(drawn), network=sorted(want)))
    res["render_matches_data"] = dict(passed=not mism, mismatches=mism[:10])

    # 3 names visible
    named = [meta.get("origin"), meta.get("dest")]
    need = [labels.get(s) for s in named if s]
    texts = set(labels.values())
    missing = [S[s]["name"] for s in named if s and s not in labels]
    if qt == "transfer_station":
        need.append(task["answer"])
        if task["answer"] not in texts:
            missing.append(task["answer"])
    in_q = all(labels.get(s) in task["question"] for s in named if s)
    res["names_visible"] = dict(passed=not missing and in_q, missing=missing)

    # 4 OCR: read each needed label at the position the renderer reported, compare with the expected text
    try:
        import pytesseract
        img = Image.open(png_path).convert("L")
        H = img.height
        norm = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())
        L = data["layout"]["labels"]
        bx = lambda v: v.get("text_bbox_px", v["bbox_px"])
        targets = [(labels[s_], bx(L[s_])) for s_ in named if s_ in L]
        if qt == "transfer_station":
            targets += [(v["text"], bx(v)) for v in L.values() if v["text"] == task["answer"]][:1]
        found = {}
        for n, (x0, y0, x1, y1) in targets:
            crop = img.crop((max(0, x0 - 6), max(0, H - y1 - 6), x1 + 6, H - y0 + 6))
            crop = crop.resize((crop.width * 3, crop.height * 3), Image.LANCZOS)
            txt = pytesseract.image_to_string(crop, config="--psm 7")
            from difflib import SequenceMatcher
            found[n] = norm(n) in norm(txt) or SequenceMatcher(None, norm(n), norm(txt)).ratio() >= 0.8
        res["ocr_names"] = dict(passed=all(found.values()), found=found)
    except Exception as e:
        res["ocr_names"] = dict(passed=None, error=repr(e))

    # no station involved in the task may have a marker sitting on a line that does not serve it
    involved = {S[x]["name"] for x in named if x}
    for t_ in meta.get("trips", []):
        for leg in t_:
            involved |= {S[leg[1]]["name"], S[leg[2]]["name"]}
    for x in meta.get("path", []):
        involved.add(S[x]["name"])
    bad_ = [o for o in data["layout"].get("overlaps", []) if o["kind"] == "marker/foreign-line"
            and o["a"].split(":")[0] in involved]
    res["markers_clear_of_other_lines"] = dict(passed=not bad_, conflicts=bad_[:6])

    # part-time (hollow) stops make trip answers debatable ("some trips skip it"): exclude such maps
    pt_ = data["layout"].get("part_time", [])
    res["no_part_time_stops"] = dict(passed=not pt_, part_time=pt_)

    # 5 uniqueness (stored by generator), 6 memory trap
    # every named station's label must be unambiguous (closer to its own markers than to any other station's)
    amb = [labels.get(s_) for s_ in named if s_ and data["layout"]["labels"].get(s_, {}).get("ambiguous")]
    if qt == "transfer_station":
        amb += [v["text"] for v in data["layout"]["labels"].values() if v["text"] == task["answer"] and v.get("ambiguous")]
    res["labels_unambiguous"] = dict(passed=not amb, ambiguous=amb)
    if qt in ("reroute_lines", "transfer_station", "accessible_route"):
        res["unique_answer"] = dict(passed=res["answer_recomputed"].get("passed", False))
    else:
        res["unique_answer"] = dict(passed=True, note="integer minimum is unique by definition")
    if data["level"] >= 2:
        normal = meta.get("normal_answer")
        same = (normal == task["answer"]) or (isinstance(normal, list) and (task["answer"] in normal
                                                                           or [task["answer"]] == normal))
        res["memory_trap"] = dict(passed=not same, normal_answer=normal)

    # 7 legibility after downscale
    w, h = Image.open(png_path).size
    f = min(1.0, 1568 / max(w, h))
    from generator.families.subway.render import STYLES
    chip_px = STYLES[data["style"]]["chip_pt"] * 0.66 * 150 / 72 * f
    res["chip_legibility"] = dict(passed=chip_px >= 9, chip_letter_px_after_downscale=round(chip_px, 1),
                                  image_px=[w, h])
    return res
