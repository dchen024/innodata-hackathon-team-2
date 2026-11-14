"""Render a schematic subway map of one region from data/subway_graph.json.

Generic transit-diagram conventions (octilinear lines, parallel route bundles, white interchange markers) on our
own computed layout. Deliberately NOT used: the MTA logo or name, the official map's artwork/layout, its
circular route bullets (we use rounded-square badges), or its copyright text.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict, deque
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import FancyBboxPatch, Polygon

from generator.families.subway.layout import (idw_warp, octi_path, octilinear_relax, offset_polyline, project, rotate,
                                              simplify)

ROOT = Path(__file__).resolve().parents[3]
GRAPH = ROOT / "data" / "subway_graph.json"
LAND = ROOT / "data" / "nyc_boroughs.geojson"   # NYC Open Data borough boundaries, shoreline-clipped

REGIONS = {
    "lower_manhattan_downtown_brooklyn": dict(lat=(40.684, 40.734), lon=(-74.020, -73.972),
                                              title="Lower Manhattan & Downtown Brooklyn", rot=29),
    "midtown": dict(lat=(40.735, 40.770), lon=(-74.005, -73.955), title="Midtown Manhattan", rot=29),
    "north_brooklyn": dict(lat=(40.660, 40.715), lon=(-73.990, -73.900), title="North & Central Brooklyn"),
    "upper_manhattan_bronx": dict(lat=(40.790, 40.850), lon=(-73.960, -73.900), title="Upper Manhattan & South Bronx", rot=29),
    "full_system": dict(lat=(40.570, 40.905), lon=(-74.035, -73.745), title="New York City (all lines)", rot=29,
                        scale=185),
    "western_queens": dict(lat=(40.735, 40.775), lon=(-73.960, -73.860), title="Western Queens"),
}

STYLES = {
    "clean": dict(water="#CFE0EF", land="#FFFFFF", header="#1E2933", header_text="white", label="#1A1A1A",
                  boro="#C9CED3", line_pt=10.2, gap_pt=11.8, chip_pt=10.4, font="DejaVu Sans"),
    "print": dict(water="#DCE6EC", land="#F7F4EC", header="#3A3A3A", header_text="white", label="#202020",
                  boro="#D2CCBE", line_pt=9.6, gap_pt=11.4, chip_pt=10.0, font="DejaVu Serif"),
}


def _hull(P_):
    """Convex hull (monotone chain) of 2-D points; returns unique points for degenerate inputs."""
    pts = sorted(set(map(tuple, np.round(P_, 9))))
    if len(pts) <= 2:
        return np.array(pts)
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    h = lo[:-1] + hi[:-1]
    return np.array(h if len(h) >= 2 else pts[:2])


def complex_groups(graph, stations):
    """Free-transfer groups among `stations`: same MTA complex id (station dataset) OR a GTFS transfer.
    Returns {group key: set(stop ids)} for groups of 2+ stations."""
    S = graph["stations"]
    parent = {s: s for s in stations}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    by_cid = defaultdict(list)
    for s in sorted(stations):
        by_cid[S[s].get("complex_id", s)].append(s)
    for ms in by_cid.values():
        for m in ms[1:]:
            parent[find(m)] = find(ms[0])
    for t in graph["transfers"]:
        if t["a"] in parent and t["b"] in parent:
            parent[find(t["a"])] = find(t["b"])
    groups = defaultdict(set)
    for s in stations:
        groups[find(s)].add(s)
    return {S[min(g)]["complex_id"] + ":" + min(g): g for g in groups.values() if len(g) > 1}


def complex_head(members, stops):
    """The station whose name labels a complex: most services, ties broken by stop id (deterministic)."""
    return sorted(members, key=lambda s: (-len(stops[s]), s))[0]


def load_graph(service: str = "weekday"):
    path = GRAPH if service == "weekday" else GRAPH.with_name("subway_graph_saturday.json")
    return json.loads(path.read_text())


# ------------------------------------------------------------------------------------------------ helpers
def _express_paths(graph, keep):
    """Route each skip-stop edge along same-colour track through the stations it passes, for drawing only."""
    routes = graph["routes"]
    adj = defaultdict(set)
    for e in graph["ride_edges"]:
        if e["a"] in keep and e["b"] in keep:
            c = routes[e["route"]]["color"]
            adj[(c, e["a"])].add(e["b"])
            adj[(c, e["b"])].add(e["a"])
    paths = {}
    for e in graph["ride_edges"]:
        a, b = e["a"], e["b"]
        if a not in keep or b not in keep:
            continue
        c = routes[e["route"]]["color"]
        prev, q = {a: None}, deque([a])
        while q and b not in prev:
            u = q.popleft()
            for v in adj[(c, u)]:
                if v not in prev and not (u == a and v == b):
                    prev[v] = u
                    q.append(v)
        if b in prev:
            path = [b]
            while path[-1] != a:
                path.append(prev[path[-1]])
            path = path[::-1]
            # only a genuine pass-through: the via-stations lie along the way (no doubling back along
            # another service's express link, which would draw a local line twice)
            S = graph["stations"]
            d = lambda u, v: math.hypot((S[u]["lat"] - S[v]["lat"]) * 111.0,
                                        (S[u]["lon"] - S[v]["lon"]) * 84.0)
            via = sum(d(u, v) for u, v in zip(path, path[1:]))
            if 2 < len(path) <= 8 and via <= 1.3 * d(a, b):
                paths[(e["route"], a, b)] = path
    return paths


def _badge(ax, x, y, route, pt, font):
    s = 6.2 * pt
    ax.add_patch(FancyBboxPatch((x - s, y - s), 2 * s, 2 * s, boxstyle=f"round,pad=0,rounding_size={2.6 * pt}",
                                fc=route["color"], ec="white", lw=0.8, zorder=9))
    ax.text(x, y, route["name"], fontsize=8, fontweight="bold", color=route["text_color"], ha="center",
            va="center_baseline", zorder=10, family=font)


def _legend(fig, width_in, Ht, H_band, st, routes, pt_in):
    """Legend box in the right of the header band (our own design)."""
    W, H = 6.4, H_band - 0.22
    lax = fig.add_axes([(width_in - W - 0.15) / width_in, 1 - (H_band - 0.11) / Ht, W / width_in, H / Ht])
    lax.set_zorder(5)
    lax.set_xlim(0, W)
    lax.set_ylim(0, H)
    lax.axis("off")
    lax.add_patch(FancyBboxPatch((0, 0), W, H, boxstyle="round,pad=0,rounding_size=0.06", fc="white", ec="none"))
    kw = dict(fontsize=7.4, va="center", family=st["font"], color="#1A1A1A")
    lw, gap, cp = st["line_pt"] / 72, st["gap_pt"] / 72, st["chip_pt"] / 72
    blue, red = "#0062CF", "#D82233"
    rows = (H * 0.70, H * 0.27)

    def chip(x, y, letter):
        lax.add_patch(FancyBboxPatch((x - cp / 2, y - cp / 2), cp, cp, boxstyle=f"round,pad=0,rounding_size={cp * .4}",
                                     fc="#111111", ec="#111111", lw=0.6, zorder=3))
        lax.text(x, y, letter, fontsize=st["chip_pt"] * 0.68, fontweight="bold", ha="center", va="center_baseline",
                 zorder=4, family=st["font"], color="white")

    def lanes(x, y, n, colour):
        for k in range(n):
            yy = y + (k - (n - 1) / 2) * gap
            lax.plot([x - 0.2, x + 0.2], [yy, yy], color=colour, lw=st["line_pt"], solid_capstyle="butt", zorder=1)

    # 1 stops / passes
    x = 0.3
    lanes(x, rows[0], 2, blue)
    chip(x, rows[0] + gap / 2, "A")
    chip(x, rows[0] - gap / 2, "C")
    lax.text(x + 0.3, rows[0], "Marker on the line:\nthat service stops here", **kw)
    lanes(x, rows[1], 2, blue)
    chip(x, rows[1] - gap / 2, "C")
    lax.text(x + 0.3, rows[1], "No marker: that service passes\nwithout stopping (express)", **kw)
    # 2 transfers
    x = 2.45
    lanes(x, rows[0], 2, blue)
    lax.plot([x, x + 0.0001], [rows[0] - gap / 2, rows[0] + gap / 2], color="black", lw=st["chip_pt"] + 5,
             solid_capstyle="round", zorder=2)
    lax.plot([x, x + 0.0001], [rows[0] - gap / 2, rows[0] + gap / 2], color="white", lw=st["chip_pt"] + 2.4,
             solid_capstyle="round", zorder=2.1)
    chip(x, rows[0] + gap / 2, "A")
    chip(x, rows[0] - gap / 2, "2")
    lax.text(x + 0.3, rows[0], "Outlined: transfer\nwithin the station", **kw)
    xa, xb = x - 0.12, x + 0.12
    lax.plot([xa, xb], [rows[1], rows[1]], color="black", lw=6.5, solid_capstyle="round", zorder=2)
    lax.plot([xa, xb], [rows[1], rows[1]], color="white", lw=4.0, solid_capstyle="round", zorder=2.1)
    for xx, L in ((xa, "A"), (xb, "2")):
        lax.plot([xx, xx + 0.0001], [rows[1], rows[1]], color="black", lw=st["chip_pt"] + 5, solid_capstyle="round",
                 zorder=2.2)
        lax.plot([xx, xx + 0.0001], [rows[1], rows[1]], color="white", lw=st["chip_pt"] + 2.4,
                 solid_capstyle="round", zorder=2.3)
        chip(xx, rows[1], L)
    lax.text(x + 0.3, rows[1], "Joined: free transfer\nbetween stations", **kw)
    # 3 names and badges
    x = 4.55
    lanes(x, rows[0], 1, "#EB6800")
    lax.add_patch(FancyBboxPatch((x - cp / 2, rows[0] - cp / 2), cp, cp, boxstyle=f"round,pad=0,rounding_size={cp * .4}",
                                 fc="white", ec="#111111", lw=1.3, zorder=3))
    lax.text(x, rows[0], "D", fontsize=st["chip_pt"] * 0.68, fontweight="bold", ha="center", va="center_baseline",
             zorder=4, family=st["font"])
    lax.text(x + 0.3, rows[0], "Hollow marker: part-time stop\n(some daytime trips skip it)", **kw)
    r = next(iter(routes.values()))
    s = 0.09
    lax.add_patch(FancyBboxPatch((x - s, rows[1] - s), 2 * s, 2 * s, boxstyle="round,pad=0,rounding_size=0.035",
                                 fc=r["color"], ec="none"))
    lax.text(x, rows[1], r["name"], fontsize=7.5, fontweight="bold", color=r["text_color"], ha="center",
             va="center_baseline", family=st["font"])
    lax.text(x + 0.18, rows[1], "Route continues\nbeyond map / terminal", **kw)

# ------------------------------------------------------------------------------------------------ render
def render_map(graph: dict, png_path: str, region="midtown", style: str = "clean",
               show_minutes: bool = False, width_in: float = 11.0, dpi: int = 150,
               service_change: dict | None = None) -> dict:
    """region: a REGIONS key or a dict(lat=(lo,hi), lon=(lo,hi), title=..., rot=deg, scale=pt per km).
    service_change: None, or
        {"kind": "suspend", "routes": [...], "from": stop_id, "to": stop_id, "notice": [lines]}
        {"kind": "skip", "station": stop_id, "routes": [...], "notice": [lines]}"""
    st = STYLES[style]
    reg = REGIONS[region] if isinstance(region, str) else region
    S, routes = graph["stations"], graph["routes"]
    rank = {r: i for i, r in enumerate(routes)}
    (la0, la1), (lo0, lo1) = reg["lat"], reg["lon"]
    mla, mlo = (la1 - la0) * 0.6, (lo1 - lo0) * 0.6
    lat0, lon0 = (la0 + la1) / 2, (lo0 + lo1) / 2
    keep = [s for s, v in S.items() if la0 - mla <= v["lat"] <= la1 + mla and lo0 - mlo <= v["lon"] <= lo1 + mlo]
    in_view = {s for s in keep if la0 <= S[s]["lat"] <= la1 and lo0 <= S[s]["lon"] <= lo1}
    # also lay out every station one stop beyond the view, so lines that leave the map are drawn (and stop chips
    # at the edge are correct) even when the next stop is far away
    keep_set = set(keep)
    base = set(keep)
    for e in graph["ride_edges"]:
        if e["a"] in base and e["b"] not in keep_set:
            keep.append(e["b"]); keep_set.add(e["b"])
        elif e["b"] in base and e["a"] not in keep_set:
            keep.append(e["a"]); keep_set.add(e["a"])
    idx = {s: i for i, s in enumerate(keep)}

    # ---- layout
    gx, gy = project([S[s]["lat"] for s in keep], [S[s]["lon"] for s in keep], lat0, lon0)
    rot = reg.get("rot", 0)
    geo = rotate(np.stack([gx, gy], 1), rot)
    xpaths = _express_paths(graph, set(keep))
    draw_pairs = defaultdict(set)                    # (a,b) sorted -> routes drawn along it
    stops = defaultdict(set)                         # station -> routes stopping
    for e in graph["ride_edges"]:
        if e["a"] not in idx or e["b"] not in idx:
            continue
        stops[e["a"]].add(e["route"])
        stops[e["b"]].add(e["route"])
        path = xpaths.get((e["route"], e["a"], e["b"]), [e["a"], e["b"]])
        for u, v in zip(path, path[1:]):
            draw_pairs[tuple(sorted((u, v)))].add(e["route"])
    # one connector chain per complex (minimum spanning tree), not every pair
    comp = {}
    gkey = {}
    for k_, g_ in complex_groups(graph, set(keep)).items():
        comp[k_] = g_
        for m_ in g_:
            gkey[m_] = k_
    passes = defaultdict(set)                        # station -> routes drawn through it that do NOT stop
    skippers = set()                                 # routes that skip stations somewhere (express patterns)
    for (r, a, b), path in xpaths.items():
        skippers.add(r)
        for m in path[1:-1]:
            passes[m].add(r)
    for m in passes:
        passes[m] -= stops[m]
    tlinks = []
    for members in comp.values():
        members = sorted(members)
        done, todo = {members[0]}, set(members[1:])
        while todo:
            _, a, b = min((float(np.hypot(*(geo[idx[a]] - geo[idx[b]]))), a, b) for a in done for b in todo)
            tlinks.append((idx[a], idx[b]))
            done.add(b)
            todo.discard(b)
    suspended, no_stop = set(), set()                # {(route, seg key)}, {(station, route)}
    sc = service_change or {}
    if sc.get("kind") == "suspend":
        for r in sc["routes"]:
            adj = defaultdict(list)
            for e in graph["ride_edges"]:
                if e["route"] == r and e["a"] in idx and e["b"] in idx:
                    adj[e["a"]].append(e["b"])
                    adj[e["b"]].append(e["a"])
            prev, q = {sc["from"]: None}, deque([sc["from"]])
            while q:
                u = q.popleft()
                for v in adj[u]:
                    if v not in prev:
                        prev[v] = u
                        q.append(v)
            if sc["to"] not in prev:
                continue
            chain = [sc["to"]]
            while chain[-1] != sc["from"]:
                chain.append(prev[chain[-1]])
            for u, v in zip(chain, chain[1:]):
                path = xpaths.get((r, u, v)) or (xpaths.get((r, v, u)) or [v, u])[::-1]
                for a_, b_ in zip(path, path[1:]):
                    suspended.add((r, tuple(sorted((a_, b_)))))
            for m in chain[1:-1]:
                no_stop.add((m, r))
            # an end of the suspended stretch loses the route too if no other service of it remains there
            cut = {tuple(sorted(p_)) for p_ in zip(chain, chain[1:])}
            for end in (chain[0], chain[-1]):
                if not any(tuple(sorted((end, v))) not in cut for v in adj[end]):
                    no_stop.add((end, r))
    elif sc.get("kind") == "skip":
        for r in sc["routes"]:
            no_stop.add((sc["station"], r))
    # complex stations sit just far enough apart for their chip rows not to collide
    km_per_pt = 1 / reg.get("scale", 235)
    link_len = [((len(stops[keep[i]]) + len(stops[keep[j]])) / 2 * st["gap_pt"] + st["chip_pt"] * 0.4) * km_per_pt
                for i, j in tlinks]
    pos = octilinear_relax(geo, [(idx[a], idx[b]) for a, b in draw_pairs], tlinks, min_sep=reg.get("min_sep", 0.36),
                           link_len=link_len)
    # transfer complexes: snap their stations onto ONE horizontal row, side by side, spaced by marker width
    for cid_, members in sorted(comp.items()):
        ms = sorted(members, key=lambda m: pos[idx[m]][0])
        if len(ms) < 2:
            continue
        ids = [idx[m] for m in ms]
        yc, xc = pos[ids, 1].mean(), pos[ids, 0].mean()
        widths = [(max(len(stops[m]), 1) * st["gap_pt"] + st["chip_pt"] * 0.9) * km_per_pt for m in ms]
        total = sum(widths)
        x = xc - total / 2
        for m, w in zip(ms, widths):
            pos[idx[m]] = (x + w / 2, yc)
            x += w
    # keep rows from running into neighbouring stations: 1-D push apart along x for stations sharing a row
    wid = {s: (max(len(stops[s]), 1) * st["gap_pt"] + st["chip_pt"] * 1.2) * km_per_pt for s in keep}
    cxid = {s: gkey.get(s, s) for s in keep}
    row_h = st["chip_pt"] * 1.6 * km_per_pt
    for _ in range(40):
        moved = False
        order_x = sorted(keep, key=lambda s: pos[idx[s]][0])
        for i_, a_ in enumerate(order_x):
            for b_ in order_x[i_ + 1:i_ + 12]:
                if cxid[a_] == cxid[b_]:
                    continue
                pa_, pb_ = pos[idx[a_]], pos[idx[b_]]
                need = (wid[a_] + wid[b_]) / 2
                if abs(pa_[1] - pb_[1]) < row_h and pb_[0] - pa_[0] < need:
                    shift = (need - (pb_[0] - pa_[0])) / 2 + 1e-4
                    for grp, sgn in ((a_, -1), (b_, 1)):          # move whole complexes together
                        for m in keep:
                            if cxid[m] == cxid[grp]:
                                pos[idx[m]][0] += sgn * shift
                    moved = True
        if not moved:
            break
    # rows that still collide after the sideways push: drop the eastern row just below the other one
    for _ in range(30):
        boxes_g = {}
        for s_ in keep:
            k_ = cxid[s_]
            x_, y_ = pos[idx[s_]]
            b_ = boxes_g.get(k_)
            boxes_g[k_] = (min(x_ - wid[s_] / 2, b_[0]) if b_ else x_ - wid[s_] / 2,
                           max(x_ + wid[s_] / 2, b_[1]) if b_ else x_ + wid[s_] / 2,
                           y_ if not b_ else (b_[2] + y_) / 2)
        hit = None
        keys_ = sorted(boxes_g, key=lambda k_: boxes_g[k_][0])
        for i_, ka in enumerate(keys_):
            for kb in keys_[i_ + 1:]:
                A_, B_ = boxes_g[ka], boxes_g[kb]
                if B_[0] >= A_[1]:
                    break
                if abs(A_[2] - B_[2]) < row_h:
                    hit = (ka, kb, A_, B_)
                    break
            if hit:
                break
        if not hit:
            break
        ka, kb, A_, B_ = hit
        dy_ = row_h * 1.15 - (A_[2] - B_[2])           # move the eastern row below the western one
        for s_ in keep:
            if cxid[s_] == kb:
                pos[idx[s_]][1] -= dy_
    P = {s: pos[idx[s]] for s in keep}

    # ---- view box from in-view stations
    V = np.array([P[s] for s in sorted(in_view)])
    pad = 0.45
    x0, y0 = V.min(0) - pad
    x1, y1 = V.max(0) + pad
    # fixed map scale (points per km) so chips and labels keep their size; the image grows instead of crowding
    if "width" in reg:
        width_in = reg["width"]
    else:
        width_in = (x1 - x0) * reg.get("scale", 235) / 72
        if width_in < 12.5:                          # leave room for title + legend in the header
            extra = (12.5 / width_in - 1) * (x1 - x0) / 2
            x0, x1, width_in = x0 - extra, x1 + extra, 12.5
    notice = (service_change or {}).get("notice") or []
    N_band = (0.32 + 0.2 * len(notice)) if notice else 0.0
    H_band = 1.15 + N_band
    height_in = width_in * (y1 - y0) / (x1 - x0)
    fig = plt.figure(figsize=(width_in, height_in + H_band), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, height_in / (height_in + H_band)])
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fc=st["water"], ec="none", zorder=0))
    pt = (x1 - x0) / (width_in * 72)
    # every station that lands inside the drawn map counts as "on the map": it gets chips AND a label, and the
    # task planner uses exactly this set (no unlabelled stations a reader could route through)
    m_ = 0.15
    in_view = {s for s in keep if x0 + m_ <= P[s][0] <= x1 - m_ and y0 + m_ <= P[s][1] <= y1 - m_}

    # ---- land, warped with the same displacement field as the stations
    boro_pts = defaultdict(list)
    if LAND.exists():
        gj = json.loads(LAND.read_text())
        for f in gj["features"]:
            name = f["properties"].get("boroname", "")
            for poly in f["geometry"]["coordinates"]:
                ring = np.array(poly[0])
                lx, ly = project(ring[:, 1], ring[:, 0], lat0, lon0)
                r = rotate(np.stack([lx, ly], 1), rot)
                bx0, by0 = geo.min(0) - 1.5
                bx1, by1 = geo.max(0) + 1.5
                if r[:, 0].max() < bx0 or r[:, 0].min() > bx1 or r[:, 1].max() < by0 or r[:, 1].min() > by1:
                    continue
                r = simplify(r, 0.16)
                if len(r) < 4:
                    continue
                w = idw_warp(r, geo, pos)
                ax.add_patch(Polygon(w, closed=True, fc=st["land"], ec="#A9BCCB", lw=0.8, zorder=0.5,
                                     joinstyle="round"))
                inside = w[(w[:, 0] > x0) & (w[:, 0] < x1) & (w[:, 1] > y0) & (w[:, 1] < y1)]
                if len(inside) > 20:
                    boro_pts[name].append(inside)
    for name, chunks in boro_pts.items():
        pts_ = np.concatenate(chunks)
        cx, cy = np.median(pts_, 0)
        cx = float(np.clip(cx, x0 + (x1 - x0) * 0.2, x1 - (x1 - x0) * 0.2))
        cy = float(np.clip(cy, y0 + (y1 - y0) * 0.08, y1 - (y1 - y0) * 0.08))
        ax.text(cx, cy, name, fontsize=30, fontweight="bold", color=st["boro"], ha="center", va="center",
                zorder=0.8, family=st["font"])

    # ---- consistent lane orientation along connected segments (BFS)
    segs = {k: sorted(v, key=rank.get) for k, v in draw_pairs.items()}
    nb = defaultdict(list)
    for k in segs:
        nb[k[0]].append(k)
        nb[k[1]].append(k)
    sign = {}
    for start in segs:
        if start in sign:
            continue
        sign[start] = 1
        q = deque([start])
        while q:
            s1 = q.popleft()
            for v in s1:
                m1 = sign[s1] * (1 if s1[1] == v else -1)
                for s2 in nb[v]:
                    if s2 not in sign:
                        sign[s2] = m1 * (1 if s2[0] == v else -1)
                        q.append(s2)

    lane_xy = defaultdict(dict)                       # station -> route -> lane point
    drawn_lines = []
    gap = st["gap_pt"] * pt
    lane_off = {}
    for k, rs in segs.items():
        for i, r in enumerate(rs):
            lane_off[(k, r)] = sign[k] * (i - (len(rs) - 1) / 2) * gap
    geom = {k: np.array(octi_path(tuple(P[k[0]]), tuple(P[k[1]]))) for k in segs}
    route_segs = defaultdict(list)
    for k, rs in segs.items():
        for r in rs:
            route_segs[r].append(k)

    def chains(r):
        adj = defaultdict(list)
        for k in route_segs[r]:
            adj[k[0]].append(k[1])
            adj[k[1]].append(k[0])
        used, out = set(), []
        starts = sorted(n for n in adj if len(adj[n]) != 2) + sorted(adj)
        for s0 in starts:
            for nb_ in sorted(adj[s0]):
                key = tuple(sorted((s0, nb_)))
                if key in used:
                    continue
                used.add(key)
                ch = [s0, nb_]
                while len(adj[ch[-1]]) == 2:
                    nxt = [x for x in adj[ch[-1]] if tuple(sorted((ch[-1], x))) not in used]
                    if not nxt:
                        break
                    used.add(tuple(sorted((ch[-1], nxt[0]))))
                    ch.append(nxt[0])
                out.append(ch)
        return out

    for r in sorted(route_segs, key=rank.get):
        for ch in chains(r):
            runs = []                                    # [offset, [points], [(station, vertex index)]]
            for u, v in zip(ch, ch[1:]):
                k = tuple(sorted((u, v)))
                fwd = k[0] == u
                g_ = geom[k] if fwd else geom[k][::-1]
                o = lane_off[(k, r)] * (1 if fwd else -1)
                if runs and abs(runs[-1][0] - o) < 1e-9:
                    runs[-1][1].extend(g_[1:].tolist())
                    runs[-1][2].append((v, len(runs[-1][1]) - 1))
                else:
                    runs.append([o, g_.tolist(), [(u, 0), (v, len(g_) - 1)]])
            full = []
            for o, pts_run, st_idx in runs:
                off = offset_polyline(pts_run, o)
                for sid, j in st_idx:
                    lane_xy[sid][r] = off[j]
                full.extend(off.tolist())
            full = np.array(full)
            ax.plot(full[:, 0], full[:, 1], color=routes[r]["color"], lw=st["line_pt"], solid_capstyle="round",
                    solid_joinstyle="round", zorder=2 + rank[r] * 0.001)
            drawn_lines.append(full)
    # suspended service: lane drawn pale and dashed over the affected stretch
    for r, k in sorted(suspended):
        if (k, r) not in lane_off:
            continue
        off = offset_polyline(geom[k], lane_off[(k, r)])
        ax.plot(off[:, 0], off[:, 1], color="white", lw=st["line_pt"] + 1.2, solid_capstyle="butt", zorder=2.5)
        ax.plot(off[:, 0], off[:, 1], color=routes[r]["color"], lw=st["line_pt"], alpha=0.35, dashes=(1.6, 1.1),
                dash_capstyle="butt", zorder=2.6)

    # ---- minutes on segments (true graph edges whose both ends are in view)
    minute_labels = {}
    if show_minutes:
        mins = defaultdict(list)
        for e in graph["ride_edges"]:
            if e["a"] in in_view and e["b"] in in_view and (e["route"], e["a"], e["b"]) not in xpaths:
                mins[tuple(sorted((e["a"], e["b"])))].append(e["minutes"])
        for (a, b), ms in mins.items():
            if (a, b) not in segs:
                continue
            m = sorted(ms)[len(ms) // 2]
            path = np.array(octi_path(tuple(P[a]), tuple(P[b])))
            seglen = np.hypot(*(path[1:] - path[:-1]).T)
            j = int(np.argmax(seglen))
            mid = (path[j] + path[j + 1]) / 2
            dv = path[j + 1] - path[j]
            n = np.array([-dv[1], dv[0]]) / max(np.hypot(*dv), 1e-9)
            o = ((len(segs[(a, b)]) - 1) / 2 * st["gap_pt"] + 8) * pt
            ax.text(*(mid + n * o), f"{m:g}", fontsize=6.5, color="#4A4A4A", ha="center", va="center", zorder=11,
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="#9AA5AE", lw=0.4))
            minute_labels[f"{a}-{b}"] = m

    # ---- stations: a lettered chip on every line that stops; bare line = passes without stopping.
    #      Transfer stations (lines of 2+ colours, or part of a multi-station complex) get a black outline
    #      around their chips; stations of one complex are joined by the connector bars drawn above.
    xfer = {k for t in graph["transfers"] for k in (t["a"], t["b"])}
    chip = st["chip_pt"] * pt
    markers = {}
    group_chips = defaultdict(list)
    station_chips = {}
    for s in keep:
        lanes = lane_xy.get(s)
        if not lanes:
            continue
        all_rs = [r for r in sorted(stops[s], key=rank.get) if r in lanes]
        if not all_rs:
            continue
        stop_rs = [r for r in all_rs if (s, r) not in no_stop]
        if not stop_rs:                              # no trains stop here under the service change
            c_ = np.mean([lanes[r] for r in all_rs], 0)
            ax.plot([c_[0]], [c_[1]], "o", ms=st["chip_pt"] * 1.15, mfc="white", mec="#7A8288", mew=1.4, zorder=6.5)
            ax.text(c_[0], c_[1], "×", fontsize=st["chip_pt"] * 0.9, color="#B3261E", ha="center",
                    va="center_baseline", zorder=6.6, fontweight="bold")
            markers[s] = dict(kind="no_service", interchange=False, center=c_.tolist(),
                              r=float(st["chip_pt"] * pt), stops=[], passes=sorted(passes[s], key=rank.get))
            continue
        colours = {routes[r]["color"] for r in stop_rs}
        is_xfer = s in xfer or len(colours) >= 2
        kind = "transfer" if is_xfer else ("local" if passes[s] else ("express" if stops[s] & skippers else "local"))
        pts_ = np.array([lanes[r] for r in stop_rs])
        if s in gkey:   # complex member: clean row centred on the station
            stop_rs = sorted(stop_rs, key=lambda r: (lanes[r][0], rank[r]))
            step_c = max(st["gap_pt"] * pt, chip * 1.06)
            pts_ = np.array([P[s] + np.array([(k - (len(stop_rs) - 1) / 2) * step_c, 0.0])
                             for k in range(len(stop_rs))])
        elif len(pts_) > 1:                          # lines meeting from different directions: tidy marker row
            dmin = min(np.hypot(*(pts_[i] - pts_[j])) for i in range(len(pts_)) for j in range(i + 1, len(pts_)))
            if dmin < chip * 1.05:
                cen = pts_.mean(0)
                spread = pts_.max(0) - pts_.min(0)
                axis = np.array([1.0, 0.0]) if spread[0] >= spread[1] else np.array([0.0, 1.0])
                pts_ = np.array([cen + axis * (k - (len(pts_) - 1) / 2) * chip * 1.08 for k in range(len(pts_))])
        if len(pts_) > 1:
            dd = ((pts_[:, None] - pts_[None]) ** 2).sum(-1)
            i, j = np.unravel_index(np.argmax(dd), dd.shape)
            ends = np.array([pts_[i], pts_[j]])
        else:
            ends = np.array([pts_[0], pts_[0]])
        in_complex = s in gkey
        station_chips[s] = (stop_rs, pts_, ends)
        if in_complex:
            group_chips[gkey[s]].append(s)
        rad = np.hypot(*(ends[1] - ends[0])) / 2 + (st["chip_pt"] + 5.0) / 2 * pt
        markers[s] = dict(kind="transfer" if in_complex else kind, interchange=is_xfer or in_complex,
                          center=ends.mean(0).tolist(), r=float(rad), stops=stop_rs,
                          passes=sorted(passes[s], key=rank.get))

    # part-time stops: a service stops here on clearly fewer daytime trips than at BOTH neighbouring stops
    # (e.g. the D skipping 182-183 Sts in rush hours) -> hollow marker, as on the MTA map
    part_time = set()
    st_trips = graph.get("stop_trips", {})
    nbrs_r = defaultdict(lambda: defaultdict(set))
    for e in graph["ride_edges"]:
        nbrs_r[e["route"]][e["a"]].add(e["b"])
        nbrs_r[e["route"]][e["b"]].add(e["a"])
    for s_, (rs_, _, _) in station_chips.items():
        for r_ in rs_:
            n_ = st_trips.get(r_, {}).get(s_)
            nb_ = [st_trips.get(r_, {}).get(v) for v in nbrs_r[r_][s_]]
            nb_ = [v for v in nb_ if v]
            if n_ and len(nb_) >= 2 and n_ < 0.85 * min(nb_):
                part_time.add((s_, r_))

    def pill(points, z):
        """White pill with a black outline around a set of marker centres (hull; capsule when collinear)."""
        w_pt = st["chip_pt"] + 5.4
        H_ = _hull(np.asarray(points))
        if len(H_) <= 2:
            e_ = H_ if len(H_) == 2 else np.array([H_[0], H_[0]])
            ax.plot(e_[:, 0], e_[:, 1], color="black", lw=w_pt, solid_capstyle="round", zorder=z)
            ax.plot(e_[:, 0], e_[:, 1], color="white", lw=w_pt - 3.0, solid_capstyle="round", zorder=z + 0.05)
        else:
            ax.add_patch(Polygon(H_, closed=True, fc="black", ec="black", lw=w_pt, joinstyle="round", zorder=z))
            ax.add_patch(Polygon(H_, closed=True, fc="white", ec="white", lw=w_pt - 3.0, joinstyle="round",
                                 zorder=z + 0.05))

    # complexes: one pill around all member markers when they sit together; otherwise a pill per station
    # joined by thin black connector lines (as on the 2026 map)
    pilled = set()
    pill_boxes = []
    for cid_, members_all in sorted(group_chips.items()):
        by_name = defaultdict(list)
        for m in members_all:
            by_name[S[m]["name"]].append(m)
        parts = []
        for nm, members in sorted(by_name.items()):
            allp = np.concatenate([station_chips[m][1] for m in members])
            hull_ = _hull(allp)
            thick = 0.0
            if len(hull_) >= 3:
                def _width(k, hull_=hull_, allp=allp):
                    e_ = hull_[(k + 1) % len(hull_)] - hull_[k]
                    d_ = allp - hull_[k]
                    return np.max(np.abs(e_[0] * d_[:, 1] - e_[1] * d_[:, 0])) / max(np.hypot(*e_), 1e-9)
                thick = min(_width(k) for k in range(len(hull_)))
            if len(members) > 1 and thick <= chip * 1.3:     # same-name platforms: one pill
                pill(allp, 6.0)
                hw = (st["chip_pt"] + 5.4) / 2 * pt
                pill_boxes.append((*(allp.min(0) - hw), *(allp.max(0) + hw)))
                pilled.update(members)
                cen_ = allp.mean(0)
                rad_ = float(np.max(np.hypot(*(allp - cen_).T))) + hw
                for m in members:
                    markers[m].update(own_center=markers[m]["center"], own_r=markers[m]["r"],
                                      center=cen_.tolist(), r=rad_)
            parts.append(allp)
        # differently named parts of one complex (Times Sq <-> Port Authority): thin connector, edge to edge
        if len(parts) > 1:
            done_p, todo_p = {0}, set(range(1, len(parts)))
            while todo_p:
                best_c = None
                for i_ in done_p:
                    for j_ in todo_p:
                        d_ = np.hypot(*(parts[i_][:, None, :] - parts[j_][None, :, :]).transpose(2, 0, 1))
                        k_ = np.unravel_index(np.argmin(d_), d_.shape)
                        if best_c is None or d_[k_] < best_c[0]:
                            best_c = (d_[k_], i_, j_, parts[i_][k_[0]], parts[j_][k_[1]])
                _, i_, j_, pa_, pb_ = best_c
                ax.plot([pa_[0], pb_[0]], [pa_[1], pb_[1]], color="black", lw=2.4, solid_capstyle="round",
                        zorder=5.9)
                done_p.add(j_)
                todo_p.discard(j_)
    for s, (stop_rs, pts_, ends) in station_chips.items():
        if markers[s]["interchange"] and s not in pilled:
            pill(pts_, 6.0)
        if len(pts_) > 1:                            # bar joining the markers across the bundle
            ax.plot(ends[:, 0], ends[:, 1], color="#111111", lw=3.0, solid_capstyle="round", zorder=6.3)
        for r, (x, y) in zip(stop_rs, pts_):
            part = (s, r) in part_time
            ax.add_patch(FancyBboxPatch((x - chip / 2, y - chip / 2), chip, chip,
                                        boxstyle=f"round,pad=0,rounding_size={chip * 0.4}",
                                        fc="white" if part else "#111111", ec="#111111", lw=1.3 if part else 0.6,
                                        zorder=6.5))
            ax.text(x, y, routes[r]["name"], fontsize=st["chip_pt"] * 0.68, fontweight="bold",
                    color="#111111" if part else "white", ha="center", va="center_baseline", zorder=6.6,
                    family=st["font"])

    # ---- badges where a route leaves the view, and at termini in view
    deg = defaultdict(lambda: defaultdict(int))
    for e in graph["ride_edges"]:
        deg[e["route"]][e["a"]] += 1
        deg[e["route"]][e["b"]] += 1
    badges, placed = [], []
    for (a, b), rs in segs.items():
        ia, ib = a in in_view, b in in_view
        if ia == ib:
            continue
        sin, sout = (a, b) if ia else (b, a)
        pa, pb = P[sin], P[sout]
        t_edge = 1.0
        for lo, hi, p, q in ((x0, x1, pa[0], pb[0]), (y0, y1, pa[1], pb[1])):
            if q != p:
                for bound in (lo, hi):
                    t = (bound - p) / (q - p)
                    if 0 < t < t_edge:
                        t_edge = t
        base = pa + (pb - pa) * t_edge * 0.86
        dv = (pb - pa) / max(np.hypot(*(pb - pa)), 1e-9)
        n = np.array([-dv[1], dv[0]])
        for i, r in enumerate(rs):
            c = base + n * (i - (len(rs) - 1) / 2) * 14 * pt
            if any(np.hypot(*(c - q)) < 13 * pt for q in placed):
                continue
            placed.append(c)
            badges.append(dict(route=r, at=c.tolist()))
    for s in sorted(in_view):
        for r in sorted(stops[s], key=rank.get):
            if deg[r][s] == 1 and s in lane_xy and r in lane_xy[s]:
                c = np.array(lane_xy[s][r]) + np.array([0, -16 * pt])
                if any(np.hypot(*(c - q)) < 13 * pt for q in placed):
                    c = c + np.array([16 * pt, 0])
                placed.append(c)
                badges.append(dict(route=r, at=c.tolist(), terminal=s))
    clear = 13 * pt
    for bd in badges:                                # nudge badges off station boxes and chips
        c = np.array(bd["at"])
        for _ in range(12):
            hit = [m for m in markers.values() if np.hypot(*(c - np.array(m["center"]))) < m["r"] + clear]
            if not hit:
                break
            m = hit[0]
            v = c - np.array(m["center"])
            v = v / max(np.hypot(*v), 1e-9) if np.hypot(*v) > 1e-9 else np.array([0.0, -1.0])
            c = np.array(m["center"]) + v * (m["r"] + clear * 1.05)
        bd["at"] = c.tolist()
        _badge(ax, *bd["at"], routes[bd["route"]], pt, st["font"])

    # ---- station labels: greedy placement, avoiding markers, badges, other labels
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    taken = []
    for bd in badges:                                # final (nudged) badge positions
        px, py = ax.transData.transform(bd["at"])
        taken.append((px - 11, py - 11, px + 11, py + 11))
    for bx0, by0, bx1, by1 in pill_boxes:
        (qx0, qy0), (qx1, qy1) = ax.transData.transform([(bx0, by0), (bx1, by1)])
        taken.append((qx0, qy0, qx1, qy1))
    hw_px = (st["chip_pt"] + 5.4) / 2 * dpi / 72
    for s, m in markers.items():
        if s in station_chips:                       # the markers' real rectangle, not a bounding circle
            q = ax.transData.transform(station_chips[s][1])
            taken.append((q[:, 0].min() - hw_px, q[:, 1].min() - hw_px, q[:, 0].max() + hw_px, q[:, 1].max() + hw_px))
        else:
            px, py = ax.transData.transform(m.get("own_center", m["center"]))
            rp = m.get("own_r", m["r"]) / pt * dpi / 72
            taken.append((px - rp, py - rp, px + rp, py + rp))
    occ = set()
    CELL = 4
    for line in drawn_lines:
        px = ax.transData.transform(line)
        for (xa, ya), (xb, yb) in zip(px, px[1:]):
            n = max(int(math.hypot(xb - xa, yb - ya) / 2), 1)
            for t in np.linspace(0, 1, n + 1):
                occ.add((int((xa + (xb - xa) * t) // CELL), int((ya + (yb - ya) * t) // CELL)))

    def line_hits(box):
        return sum((i, j) in occ for i in range(int(box[0] // CELL), int(box[2] // CELL) + 1)
                   for j in range(int(box[1] // CELL), int(box[3] // CELL) + 1))

    chip_px = {s_: ax.transData.transform(pts_).tolist() for s_, (rs_, pts_, _) in station_chips.items()}
    for s_, m_ in markers.items():
        if s_ not in chip_px:
            chip_px[s_] = [ax.transData.transform(m_["center"]).tolist()]
    groups = defaultdict(list)                       # one label per station name
    for s in sorted(in_view & set(markers)):
        groups[(S[s]["complex_id"], S[s]["name"])].append(s)
    cands = [(1, 0, "left", "center"), (-1, 0, "right", "center"), (0, 1, "center", "bottom"),
             (0, -1, "center", "top"), (1, 1, "left", "bottom"), (1, -1, "left", "top"),
             (-1, 1, "right", "bottom"), (-1, -1, "right", "top")]
    halo = [pe.withStroke(linewidth=2.6, foreground=st["land"])]
    labels = {}
    order_ = sorted(groups.values(), key=lambda m: (not any(markers[s]["interchange"] for s in m), S[m[0]]["name"]))
    for members in order_:
        head = complex_head(members, stops)
        oc = lambda s_: markers[s_].get("own_center", markers[s_]["center"])
        orr = lambda s_: markers[s_].get("own_r", markers[s_]["r"])
        cen = np.mean([oc(s) for s in members], 0)
        g = max(float(np.hypot(*(np.array(oc(s)) - cen))) + orr(s) for s in members) + 3 * pt
        inter = any(markers[s]["interchange"] for s in members)
        names = []
        for r in sorted({r for s in members for r in stops[s]}, key=rank.get):
            if routes[r]["name"] not in names:
                names.append(routes[r]["name"])
        text = S[head]["name"]
        best = None
        accessible = any(S[s_].get("ada") == 1 for s_ in members)
        own_px = np.array([q for s_ in members for q in chip_px.get(s_, [])])
        other_px = np.array([q for s2, qs in chip_px.items() if s2 not in members and S[s2]["name"] != text
                             for q in qs]) if chip_px else np.zeros((0, 2))
        fs = (8 if inter else 7.4) * reg.get("label_scale", 1.0)
        icon_w = fs * 1.45 * dpi / 72 if accessible else 0.0

        def box_dist(box, P_):
            if len(P_) == 0:
                return 1e9
            dx_ = np.maximum(np.maximum(box[0] - P_[:, 0], 0), P_[:, 0] - box[2])
            dy_ = np.maximum(np.maximum(box[1] - P_[:, 1], 0), P_[:, 1] - box[3])
            return float(np.min(np.hypot(dx_, dy_)))

        # candidate anchors hug this station's OWN markers (just outside the pill), then step outward
        own_d_pts = np.array([q for s_ in members for q in (station_chips[s_][1].tolist() if s_ in station_chips
                                                              else [markers[s_]["center"]])])
        lo_, hi_ = own_d_pts.min(0), own_d_pts.max(0)
        pad0 = (st["chip_pt"] + 5.4) / 2 * pt + 2.5 * pt
        mx_, my_ = (lo_ + hi_) / 2
        for ring, (dx, dy, ha, va) in [(r_, c) for r_ in (1.0, 1.6, 2.4) for c in cands]:
            pad = pad0 * ring
            ax_ = {1: hi_[0] + pad, -1: lo_[0] - pad, 0: mx_}[dx]
            ay_ = {1: hi_[1] + pad, -1: lo_[1] - pad, 0: my_}[dy]
            txt = ax.text(ax_, ay_, text, fontsize=fs,
                          ha=ha, va=va, zorder=12, family=st["font"], color=st["label"], linespacing=1.05,
                          multialignment={"left": "left", "right": "right"}.get(ha, "center"),
                          fontweight="bold" if inter else "normal", path_effects=halo)
            bb = txt.get_window_extent(rend)
            box = (bb.x0 - 1, bb.y0 - 1, bb.x1 + 1 + icon_w, bb.y1 + 1)
            fits = 2 <= box[0] and box[2] <= fig.bbox.width - 2 and ax.bbox.y0 + 2 <= box[1] and box[3] <= ax.bbox.y1 - 2
            clash = any(not (box[2] < t[0] or t[2] < box[0] or box[3] < t[1] or t[3] < box[1]) for t in taken)
            if fits and not clash:
                # the name must sit closer to its own markers than to any other station's (no misreading)
                own_d, other_d = box_dist(box, own_px), box_dist(box, other_px)
                ambiguous = other_d <= own_d + 4
                cost = line_hits(box) + (10_000 if ring > 1.6 else 3_000 if ring > 1 else 0) + \
                    (40_000 if ambiguous else 0)
                if best is None or cost < best[0]:
                    if best:
                        best[1].remove()
                    best = (cost, txt, box, ambiguous, own_d, other_d)
                    if cost == 0:
                        break
                    continue
            txt.remove()
        if best:
            taken.append(best[2])
            if accessible:                               # ISO 7001 accessibility symbol after the name
                bx1_, by0_, by1_ = best[2][2] - icon_w, best[2][1], best[2][3]
                cxy = ax.transData.inverted().transform((bx1_ + icon_w / 2 + 1, (by0_ + by1_) / 2))
                ax.text(cxy[0], cxy[1], "\u267f", fontsize=fs * 0.95, color="white", ha="center",
                        va="center", zorder=12.5, family="DejaVu Sans",
                        bbox=dict(boxstyle="round,pad=0.12,rounding_size=0.25", fc="#1F5FAD", ec="none"))
            for s in members:
                tb = list(best[2]); tb[2] -= icon_w
                labels[s] = dict(text=S[head]["name"], services=names, bbox_px=[round(v, 1) for v in best[2]],
                                 text_bbox_px=[round(float(v), 1) for v in tb],
                                 line_overlap=best[0], ambiguous=best[3], accessible=accessible,
                                 own_dist_px=round(best[4], 1), other_dist_px=round(best[5], 1))

    # ---- header band and footer
    Ht = height_in + H_band
    fig.patches.append(plt.Rectangle((0, 1 - H_band / Ht), 1, H_band / Ht, transform=fig.transFigure,
                                     fc=st["header"], ec="none", zorder=0))
    title = f"Subway  —  {reg.get('title', '')}"
    title_fs = min(17.0, (width_in - 6.9) * 72 / (0.66 * len(title)))     # never run under the legend
    fig.text(0.018, 1 - 0.36 / Ht, title, fontsize=title_fs, fontweight="bold",
             color=st["header_text"], va="center", family=st["font"])
    note = ("Weekend service, Saturday and Sunday" if service_change else "Weekday daytime service") + ("  ·  Numbers on track: typical running time between stations, in minutes"
                                        if show_minutes else "")
    fig.text(0.018, 1 - 0.72 / Ht, note, fontsize=9, color="#D5DCE2", va="center", family=st["font"])
    _legend(fig, width_in, Ht, H_band - N_band, st, routes, pt_in=1 / 72)
    if notice:
        y_top = 1 - (H_band - N_band) / Ht
        fig.patches.append(plt.Rectangle((0, y_top - N_band / Ht), 1, N_band / Ht, transform=fig.transFigure,
                                         fc="#FFD23F", ec="none", zorder=0))
        fig.text(0.018, y_top - 0.17 / Ht, "WEEKEND SERVICE CHANGE", fontsize=10.5, fontweight="bold",
                 color="#111111", va="center", family=st["font"])
        for i, line in enumerate(notice):
            fig.text(0.018, y_top - (0.38 + 0.2 * i) / Ht, line, fontsize=9.5, color="#111111", va="center",
                     family=st["font"])
    ax.text(x1 - 4 * pt, y0 + 4 * pt, "Schematic generated from public GTFS data. Not an official map.",
            fontsize=6.5, color="#5B6770", ha="right", va="bottom", zorder=12, family=st["font"])
    fig.savefig(png_path, dpi=dpi, facecolor=st["header"])
    plt.close(fig)
    # ---- audit: every marker and label in pixels; report collisions between different stations
    tr = ax.transData.transform
    half_px = chip / pt * dpi / 72 / 2
    chips_px = [(s_, r_, *tr((x_, y_))) for s_, (rs_, pts_, _) in station_chips.items() if s_ in in_view
                for r_, (x_, y_) in zip(rs_, pts_)]
    overlaps = []
    cx_ = {s_: S[s_]["complex_id"] for s_ in station_chips}
    for i_ in range(len(chips_px)):
        for j_ in range(i_ + 1, len(chips_px)):
            a1, b1 = chips_px[i_], chips_px[j_]
            if a1[0] == b1[0]:
                continue
            if abs(a1[2] - b1[2]) < 2 * half_px * 0.92 and abs(a1[3] - b1[3]) < 2 * half_px * 0.92:
                overlaps.append(dict(kind="marker/marker", a=f"{S[a1[0]]['name']}:{a1[1]}",
                                     b=f"{S[b1[0]]['name']}:{b1[1]}", same_complex=cx_[a1[0]] == cx_[b1[0]]))
    for s_, lab in labels.items():
        x0_, y0_, x1_, y1_ = lab["bbox_px"]
        for (s2, r2, px_, py_) in chips_px:
            if x0_ < px_ + half_px and px_ - half_px < x1_ and y0_ < py_ + half_px and py_ - half_px < y1_:
                overlaps.append(dict(kind="label/marker", a=lab["text"], b=f"{S[s2]['name']}:{r2}"))
    seen_l = {}
    for s_, lab in labels.items():
        seen_l[tuple(lab["bbox_px"])] = lab["text"]
    boxes_l = list(seen_l.items())
    for i_ in range(len(boxes_l)):
        for j_ in range(i_ + 1, len(boxes_l)):
            (a_, ta), (b_, tb) = boxes_l[i_], boxes_l[j_]
            if a_[0] < b_[2] and b_[0] < a_[2] and a_[1] < b_[3] and b_[1] < a_[3]:
                overlaps.append(dict(kind="label/label", a=ta, b=tb))
    # markers sitting on a ribbon of a service that does NOT stop at that station (reads as a false stop)
    lines_by_route = defaultdict(list)
    for (k_, r_), off_ in lane_off.items():
        lines_by_route[r_].append(tr(offset_polyline(geom[k_], off_)))
    lw_px = st["line_pt"] * dpi / 72 / 2
    for (s_, r_, px_, py_) in chips_px:
        grp_ = comp.get(gkey.get(s_), {s_})
        own_rs = set(passes.get(s_, ())).union(*(stops[m] for m in grp_))
        for r2, polys in lines_by_route.items():
            if r2 in own_rs or r2 in stops[s_]:
                continue
            for pl in polys:
                a_, b_ = pl[:-1], pl[1:]
                ab = b_ - a_
                l2 = np.maximum((ab ** 2).sum(1), 1e-9)
                tt = np.clip(((np.array([px_, py_]) - a_) * ab).sum(1) / l2, 0, 1)
                dd_ = np.hypot(*(a_ + tt[:, None] * ab - np.array([px_, py_])).T)
                if dd_.min() < lw_px + half_px * 0.8:
                    overlaps.append(dict(kind="marker/foreign-line", a=f"{S[s_]['name']}:{r_}", b=r2))
                    break
    for s_, lab in labels.items():
        if lab.get("ambiguous"):
            overlaps.append(dict(kind="label/closer-to-other-station", a=lab["text"], b=""))
    return dict(region=region if isinstance(region, str) else reg.get("title"), style=style, overlaps=overlaps,
                service_change=service_change, no_stop=sorted(no_stop), suspended=sorted(suspended), stations_in_view=sorted(in_view), labels=labels,
                unlabelled=sorted((in_view & set(markers)) - set(labels)), badges=badges,
                minute_labels=minute_labels, part_time=sorted(part_time), positions_km={s: P[s].round(4).tolist() for s in in_view},
                stations={s: dict(kind=markers[s]["kind"], stops=markers[s]["stops"], passes=markers[s]["passes"])
                          for s in in_view if s in markers})


if __name__ == "__main__":
    import sys
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = args[0] if args else "subway_map.png"
    region = args[1] if len(args) > 1 else "midtown"
    style = args[2] if len(args) > 2 else "clean"
    g = load_graph()
    lay = render_map(g, out, region, style, show_minutes="--minutes" in sys.argv)
    print(f"{out}: {len(lay['stations_in_view'])} stations in view, {len(lay['labels'])} labelled; unlabelled: "
          f"{[g['stations'][s]['name'] for s in lay['unlabelled']]}")
