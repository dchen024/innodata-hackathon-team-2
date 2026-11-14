"""Subway commuter tasks: a regional map with a weekend service change, and a trip-planning question whose
answer is computed by code on the modified network.

Difficulty comes from (a) reading which services stop where (lettered chips; express lines pass bare),
(b) noticing the service change (notice strip + pale dashed track + missing chips), and (c) planning a
multi-leg route. Scenarios are chosen so the weekend answer DIFFERS from the normal-service answer, so a
model that answers from memory of the NYC subway, or ignores the notice, gets it wrong.
"""
from __future__ import annotations

import heapq
from collections import defaultdict, deque

import numpy as np

from generator.base import Family, NoValidQuestion, Question
from generator.families.subway.render import complex_groups, complex_head, load_graph, render_map

VERSION = "subway-0.3.0"

# task windows: centre (lat, lon), half-size in degrees (lat, lon), rotation (Manhattan grid upright)
WINDOWS = {
    "times_sq": dict(c=(40.7545, -73.9870), h=(0.0115, 0.0125), rot=29, title="Midtown West"),
    "grand_central": dict(c=(40.7540, -73.9790), h=(0.0115, 0.0125), rot=29, title="Midtown East"),
    "union_sq": dict(c=(40.7365, -73.9930), h=(0.0115, 0.0125), rot=29, title="Union Square & Chelsea"),
    "fulton": dict(c=(40.7110, -74.0060), h=(0.0105, 0.0125), rot=29, title="Lower Manhattan"),
    "downtown_bk": dict(c=(40.6900, -73.9850), h=(0.0105, 0.0135), rot=0, title="Downtown Brooklyn"),
    "lic": dict(c=(40.7480, -73.9380), h=(0.0100, 0.0160), rot=0, title="Long Island City"),
    "uws": dict(c=(40.7900, -73.9650), h=(0.0140, 0.0130), rot=29, title="Upper Manhattan West"),
    "jackson_hts": dict(c=(40.7440, -73.8950), h=(0.0090, 0.0220), rot=0, title="Jackson Heights & Elmhurst"),
    "bway_jct": dict(c=(40.6800, -73.9100), h=(0.0110, 0.0190), rot=0, title="East New York & Bushwick"),
}

QTYPES = ["min_stops", "reroute_lines", "transfer_station", "count_stops", "accessible_route"]


def accessible_set(graph, in_view):
    """Stations a wheelchair user can use: exactly those whose printed name carries the accessibility symbol
    (the map draws one icon per station name within a complex if any platform of that name is accessible)."""
    S = graph["stations"]
    ok_names = {(S[s]["complex_id"], S[s]["name"]) for s in in_view if S[s].get("ada") == 1}
    return {s for s in in_view if (S[s]["complex_id"], S[s]["name"]) in ok_names}


_VISIBLE = {}


def visible_stations(graph, name):
    """Stations drawn (and labelled) on the window's map: the planner works on exactly this set."""
    if name not in _VISIBLE:
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            lay = render_map(graph, os.path.join(td, "probe.png"), window_region(name), "clean")
        _VISIBLE[name] = set(lay["stations_in_view"])
    return _VISIBLE[name]


def window_region(name):
    w = WINDOWS[name]
    (la, lo), (hla, hlo) = w["c"], w["h"]
    return dict(lat=(la - hla, la + hla), lon=(lo - hlo, lo + hlo), rot=w["rot"], title=w["title"], scale=250)


# ---------------------------------------------------------------------------------------------- network
def network(graph, in_view, sc=None):
    """Services after applying a service change.
    stops[station] -> routes that stop there (any ride edge touching the view counts, so a service whose next
    stop is off-map still stops here, exactly as the map draws it); ride[route] -> {(a,b)} next-stop edges
    with both ends on the map (what a rider can plan with)."""
    ride_all = defaultdict(set)
    for e in graph["ride_edges"]:
        if e["a"] in in_view or e["b"] in in_view:
            ride_all[e["route"]].add(tuple(sorted((e["a"], e["b"]))))
    sc = sc or {}
    if sc.get("kind") == "suspend":
        for r in sc["routes"]:
            adj = defaultdict(set)
            for a, b in ride_all[r]:
                adj[a].add(b)
                adj[b].add(a)
            path = _bfs_path(adj, sc["from"], sc["to"])
            if path:
                for u, v in zip(path, path[1:]):
                    ride_all[r].discard(tuple(sorted((u, v))))
    elif sc.get("kind") == "skip":
        x = sc["station"]
        for r in sc["routes"]:
            nbrs = sorted({b if a == x else a for a, b in ride_all[r] if x in (a, b)})
            ride_all[r] = {e for e in ride_all[r] if x not in e}
            if len(nbrs) == 2:                       # trains still run through: neighbours become consecutive
                ride_all[r].add(tuple(nbrs))
    stops = defaultdict(set)
    ride = defaultdict(set)
    for r, es in ride_all.items():
        for a, b in es:
            for s in (a, b):
                if s in in_view:
                    stops[s].add(r)
            if a in in_view and b in in_view:
                ride[r].add((a, b))
    return stops, ride


def _bfs_path(adj, a, b):
    prev, q = {a: None}, deque([a])
    while q:
        u = q.popleft()
        if u == b:
            break
        for v in sorted(adj[u]):
            if v not in prev:
                prev[v] = u
                q.append(v)
    if b not in prev:
        return None
    p = [b]
    while p[-1] != a:
        p.append(prev[p[-1]])
    return p[::-1]


def plan(graph, in_view, sc, origin, dest, objective="transfers", access=None):
    """Lexicographic shortest trips. objective 'transfers' = (transfers, stops); 'stops' = (stops, transfers).
    Returns (best cost, list of all optimal trips); a trip is a list of (route, board station, alight station)."""
    stops, ride = network(graph, in_view, sc)
    adj = defaultdict(list)                          # (station, route) -> [(station', route', dT, dS)]
    for r, es in sorted(ride.items()):
        for a, b in sorted(es):
            adj[(a, r)].append((b, r, 0, 1))
            adj[(b, r)].append((a, r, 0, 1))
    complex_of = {s: graph["stations"][s]["complex_id"] for s in in_view}
    walk = defaultdict(set)                          # free transfers: same complex id or GTFS transfer
    for g_ in complex_groups(graph, set(in_view)).values():
        for a_ in g_:
            walk[a_] |= g_ - {a_}
    for s in sorted(in_view):
        if access is not None and s not in access:      # cannot change trains at an inaccessible station
            continue
        for r1 in sorted(stops[s]):
            for r2 in sorted(stops[s]):
                if r1 != r2:
                    adj[(s, r1)].append((s, r2, 1, 0))
            for s2 in sorted(walk[s]):
                if access is not None and s2 not in access:
                    continue
                for r2 in sorted(stops[s2]):
                    adj[(s, r1)].append((s2, r2, 1, 0))
    key = (lambda t, n: (t, n)) if objective == "transfers" else (lambda t, n: (n, t))
    # origin and destination are station COMPLEXES (a rider "at Herald Sq" can board any of its platforms)
    # origin/destination = the named station (all same-name platforms), not other names in its complex
    cx = lambda s: sorted(m for m in ({s} | walk[s]) if graph["stations"][m]["name"] == graph["stations"][s]["name"])
    origins, dests = cx(origin), set(cx(dest))
    if access is not None:
        origins = [o_ for o_ in origins if o_ in access]
        dests = {d_ for d_ in dests if d_ in access}
    # state = (station, route, arrived_by_ride). Every non-ride step (change at a station, or a walk between
    # joined stations) costs one transfer; the trip must END with a ride into the destination.
    dist, preds = {}, defaultdict(list)
    pq = []
    for o_ in origins:
        for r in sorted(stops[o_]):
            dist[(o_, r, 0)] = key(0, 0)
            heapq.heappush(pq, (key(0, 0), o_, r, 0))
    while pq:
        d, s, r, f = heapq.heappop(pq)
        if d > dist.get((s, r, f), (9e9, 9e9)):
            continue
        t, n = (d if objective == "transfers" else (d[1], d[0]))
        for s2, r2, dt, dn in adj[(s, r)]:
            f2 = 1 if dn else 0
            nd = key(t + dt, n + dn)
            old = dist.get((s2, r2, f2))
            if old is None or nd < old:
                dist[(s2, r2, f2)] = nd
                preds[(s2, r2, f2)] = [(s, r, f)]
                heapq.heappush(pq, (nd, s2, r2, f2))
            elif nd == old:
                preds[(s2, r2, f2)].append((s, r, f))
    ends = [(dist[(d_, r, 1)], (d_, r, 1)) for d_ in sorted(dests) for r in sorted(stops[d_]) if (d_, r, 1) in dist]
    if not ends:
        return None, []
    best = min(e[0] for e in ends)
    trips = []

    def walk_back(node, acc, depth=0):
        if depth > 80 or len(trips) > 200:
            return
        if node[0] in origins and node[2] == 0 and dist[node] == key(0, 0):
            trips.append(acc[::-1])
            return
        for p in preds[node]:
            walk_back(p, acc + [p], depth + 1)

    for d, node in ends:
        if d == best:
            walk_back(node, [node])
    # legs = the rides only: (route, board station, alight station)
    out = []
    for path in trips:
        legs = []
        for (s, r, f), (s2, r2, f2) in zip(path, path[1:]):
            if f2 != 1:
                continue                             # transfer step
            if legs and legs[-1][0] == r2 and legs[-1][2] == s and (s, r, f) == (legs[-1][2], r2, f):
                legs[-1][2] = s2
            elif legs and legs[-1][0] == r2 and legs[-1][2] == s:
                legs[-1][2] = s2
            else:
                legs.append([r2, s, s2])
        legs = [tuple(l) for l in legs]
        visited = [st_ for (st_, _, _) in path]
        ridden = [st_ for i_, (st_, _, f_) in enumerate(path) if f_ == 1 or i_ == 0]
        # no U-turns / revisits (riding out and back to "arrive by train" is not a real trip), at most 3 rides
        if (not legs or any(l[1] == l[2] for l in legs) or len(set(ridden)) != len(ridden) or len(legs) > 3
                or len({l[0] for l in legs}) != len(legs)):   # never ride the same service twice
            continue
        if legs not in out:
            out.append(legs)
    if not out:
        return None, []
    return best, out


def equivalent_sequences(graph, in_view, sc, trips, access=None):
    """All service sequences that ride the SAME legs (same boarding and alighting stations) as an optimal trip,
    with any service that runs between those two stations on the map (e.g. A, C or E from 59 St to 42 St).
    These are accepted as correct answers alongside the canonical one."""
    import itertools
    _, ride = network(graph, in_view, sc)
    R = graph["routes"]
    adj = {r: defaultdict(set) for r in ride}
    for r, es in ride.items():
        for a, b in es:
            adj[r][a].add(b)
            adj[r][b].add(a)
    out = set()
    for trip in trips:
        options = []
        for (r0, a, b) in trip:
            alts = sorted(r for r in ride if a in adj[r] and _bfs_path(adj[r], a, b))
            options.append(sorted({R[r]["name"] for r in alts}))
        for combo in itertools.product(*options):
            if len(set(combo)) == len(combo):
                out.add(tuple(combo))
    return sorted(out)


# ---------------------------------------------------------------------------------------------- family
class SubwayFamily(Family):
    name = "subway"
    version = VERSION
    question_types = QTYPES
    styles = ["clean", "print"]
    references = {
        "clean": ["MTA New York City Subway map (2026 edition): lettered stop markers on each service line",
                  "MTA 'The Weekender' planned-work maps and station service-change posters"],
        "print": ["MTA New York City Subway map (April 2026 print edition, Hertz design)",
                  "MTA planned service change notices ('No 2 3 trains between ...')"],
    }

    _graph = None

    @property
    def graph(self):                                 # weekend tasks use the Saturday timetable; loaded lazily
        if SubwayFamily._graph is None:
            SubwayFamily._graph = load_graph("saturday")
        return SubwayFamily._graph

    def _scenario(self, rng, level, qtype=None):
        g = self.graph
        S = g["stations"]
        win = sorted(WINDOWS)[int(rng.integers(len(WINDOWS)))]
        reg = window_region(win)
        in_view = visible_stations(g, win)
        if len(in_view) < 12:
            raise NoValidQuestion
        stops0, ride0 = network(g, in_view)
        # service change: suspend 1-2 services sharing a stretch of 2-5 stops (level>=2), or close a station
        sc = None
        if level >= 2:
            cand = []
            for r, es in sorted(ride0.items()):
                if len(es) >= 3:
                    cand.append(r)
            if not cand:
                raise NoValidQuestion
            r = cand[int(rng.integers(len(cand)))]
            adj = defaultdict(set)
            for a, b in ride0[r]:
                adj[a].add(b)
                adj[b].add(a)
            ends_ = sorted(n for n in adj if len(adj[n]) == 1) or sorted(adj)
            start = ends_[int(rng.integers(len(ends_)))]
            far = sorted(adj, key=lambda n: -len(_bfs_path(adj, start, n) or []))[0]
            line = _bfs_path(adj, start, far)
            k = int(rng.integers(2, min(5, len(line) - 1) + 1)) if len(line) >= 3 else 0
            if k < 2:
                raise NoValidQuestion
            i0 = int(rng.integers(0, len(line) - k))
            frm, to = line[i0], line[i0 + k]
            # services running on exactly the same stops over this stretch are suspended together (e.g. 2 and 3)
            stretch = set(map(tuple, map(sorted, zip(line[i0:i0 + k], line[i0 + 1:i0 + k + 1]))))
            group = [q for q in sorted(ride0) if stretch <= ride0[q]]
            kind = "skip" if (qtype == "count_stops" or (level >= 3 and rng.random() < 0.3)) else "suspend"
            if kind == "suspend":
                names = list(dict.fromkeys(g["routes"][q]["name"] for q in group))
                who = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]
                sc = dict(kind="suspend", routes=group, **{"from": frm, "to": to},
                          notice=[f"No {who} trains between {S[frm]['name']} and {S[to]['name']}, in both "
                                  f"directions.",
                                  "Other services operate normally. Transfers are free where shown on the map."])
            else:
                x = line[i0 + 1]
                rs = sorted(stops0[x])
                names = " ".join(dict.fromkeys(g["routes"][q]["name"] for q in rs))
                sc = dict(kind="skip", station=x, routes=rs,
                          notice=[f"{S[x]['name']} is closed: {names} trains run through without stopping, in "
                                  f"both directions.", "Other stations and services operate normally."])
        return win, reg, in_view, sc

    def generate(self, seed, level, question_type, style):
        rng = np.random.default_rng(seed)
        g = self.graph
        S = g["stations"]
        for attempt in range(400):
            try:
                win, reg, in_view, sc = self._scenario(rng, level, question_type)
                q, meta = self._question(rng, in_view, sc, question_type, level)
            except NoValidQuestion:
                continue
            q.meta = meta
            data = dict(family=self.name, generator_version=self.version, seed=seed, level=level, style=style,
                        attempt=attempt, window=win, region=reg, service_change=sc, question_meta=meta,
                        stations_in_view=sorted(in_view), references=self.references[style],
                        source=g["source"])
            return data, q
        raise RuntimeError(f"no valid subway task for seed={seed} level={level} qtype={question_type}")

    # ------------------------------------------------------------------------------------------ questions
    def _names(self, in_view):
        """Visible label text per station (complexes are labelled once with the head station's name)."""
        g = self.graph
        S = g["stations"]
        stops, _ = network(g, in_view)
        groups = defaultdict(list)
        for s in sorted(in_view):
            if stops[s]:
                groups[S[s]["complex_id"]].append(s)
        # every distinct station name is printed (one label per name within a complex)
        label = {s: S[s]["name"] for m in groups.values() for s in m}
        counts = defaultdict(int)
        for members in groups.values():
            for nm in {S[s]["name"] for s in members}:
                counts[nm] += 1
        return label, counts, groups

    def _question(self, rng, in_view, sc, qtype, level):
        g = self.graph
        R = g["routes"]
        label, counts, groups = self._names(in_view)
        # endpoints: complexes whose label is unique in view (no "which 23 St?" ambiguity)
        # endpoints: uniquely named, and still served under the service change (never a closed station)
        stops_sc_, _ = network(g, in_view, sc)
        served = lambda m: any(stops_sc_[x] for x in m if label[x] == label[m[0]])
        heads = sorted(m[0] for m in groups.values() if counts[label[m[0]]] == 1 and served(m))
        if len(heads) < 4:
            raise NoValidQuestion
        rn = lambda r: R[r]["name"]

        def complex_station(s):
            return [m for m in groups.values() if s in m][0]

        if qtype == "count_stops":
            stops_sc, ride_sc = network(g, in_view, sc)
            rs_ok = sorted(q for q, es in ride_sc.items() if len(es) >= 3)
            if sc and sc.get("kind") == "skip":          # ask about a line that runs through the closed station
                rs_ok = [q for q in rs_ok if q in sc["routes"]]
            if not rs_ok:
                raise NoValidQuestion
            r = rs_ok[int(rng.integers(len(rs_ok)))]
            adj = defaultdict(set)
            for a, b in ride_sc[r]:
                adj[a].add(b)
                adj[b].add(a)
            nodes = sorted(adj)
            a, b = nodes[int(rng.integers(len(nodes)))], nodes[int(rng.integers(len(nodes)))]
            path = _bfs_path(adj, a, b)
            if not path or len(path) < 4 or counts[label[a]] != 1 or counts[label[b]] != 1:
                raise NoValidQuestion
            n_mid = len(path) - 2
            # memory trap: the count must differ from the normal-service count (level>=2)
            _, ride0 = network(g, in_view)
            adj0 = defaultdict(set)
            for x, y in ride0[r]:
                adj0[x].add(y)
                adj0[y].add(x)
            p0 = _bfs_path(adj0, a, b)
            if level >= 2 and p0 and len(p0) - 2 == n_mid:
                raise NoValidQuestion
            when = "This weekend, between" if sc else "Between"
            return (Question("count_stops",
                             f"{when} {label[a]} and {label[b]}, how many intermediate stops does a {rn(r)} train "
                             f"make? Do not count {label[a]} or {label[b]} themselves. Answer with an integer.",
                             n_mid, "integer"),
                    dict(route=r, origin=a, dest=b, path=path, normal_answer=(len(p0) - 2) if p0 else None))

        o, d = rng.choice(heads, size=2, replace=False).tolist()
        if self.graph["stations"][o]["complex_id"] == self.graph["stations"][d]["complex_id"]:
            raise NoValidQuestion
        when = "this weekend" if sc else "on a weekday"
        if qtype == "min_stops":
            best, trips = plan(g, in_view, sc, o, d, objective="stops")
            best0, _ = plan(g, in_view, None, o, d, objective="stops")
            if best is None or best[0] < 3:
                raise NoValidQuestion
            if level >= 2 and best0 is not None and best0[0] == best[0]:
                raise NoValidQuestion
            return (Question("min_stops",
                             f"A rider travels {when} from {label[o]} to {label[d]} using only the services and "
                             f"free transfers shown on this map. Walking between stations joined on the map counts "
                             f"as a transfer, and the trip ends when a train arrives at {label[d]} itself. What is the fewest number of station stops the "
                             f"trip can take? Count every station where the rider's train stops after leaving "
                             f"{label[o]}, including {label[d]}; transfers are allowed and do not add stops. "
                             f"Answer with an integer.",
                             int(best[0]), "integer"),
                    dict(origin=o, dest=d, trips=trips[:10], normal_answer=best0[0] if best0 else None))

        best, trips = plan(g, in_view, sc, o, d, objective="transfers")
        if best is None or not trips:
            raise NoValidQuestion
        seqs = {tuple(rn(l[0]) for l in t) for t in trips}
        best0, trips0 = plan(g, in_view, None, o, d, objective="transfers")
        seqs0 = {tuple(rn(l[0]) for l in t) for t in trips0}
        if qtype == "reroute_lines":
            if len(seqs) != 1 or best[0] < 1 or best[0] > 2:
                raise NoValidQuestion
            ans = list(next(iter(seqs)))
            if level >= 2 and tuple(ans) in seqs0:    # memory trap: normal-service best trips must differ
                raise NoValidQuestion
            return (Question("reroute_lines",
                             f"A rider travels {when} from {label[o]} to {label[d]} using only the services and "
                             f"free transfers shown on this map. Walking between stations joined on the map counts "
                             f"as a transfer, and the trip ends when a train arrives at {label[d]} itself. They want the fewest transfers and, among those "
                             f"trips, the fewest station stops. Which services do they ride, in order? If more than one "
                             f"service runs between the same two stations on a leg, any of them is accepted. Answer as "
                             f"a JSON list of route letters or numbers, for example [\"A\", \"7\"].",
                             ans, "sequence"),
                    dict(origin=o, dest=d, trips=trips[:10], normal_answer=sorted(seqs0),
                         accepted_answers=[list(x) for x in equivalent_sequences(g, in_view, sc, trips)]))
        if qtype == "transfer_station":
            if best[0] != 1:
                raise NoValidQuestion
            xs = set()
            for t in trips:
                # transfer must happen inside ONE named station (alight and board under the same label);
                # a walk between two differently named stations makes "which station?" ambiguous
                if len(t) != 2 or label[t[0][2]] != label[t[1][1]]:   # the one transfer must be between rides
                    raise NoValidQuestion
                xs.add(label[t[0][2]])
            if len(xs) != 1:
                raise NoValidQuestion
            xs0 = {label[t[0][2]] for t in trips0 if len(t) == 2}
            ans = next(iter(xs))
            if level >= 2 and ans in xs0:
                raise NoValidQuestion
            return (Question("transfer_station",
                             f"A rider travels {when} from {label[o]} to {label[d]} using only the services and "
                             f"free transfers shown on this map (walking between stations joined on the map counts as "
                             f"a transfer; the trip ends when a train arrives at {label[d]} itself), with exactly one transfer and, among such trips, "
                             f"the fewest station stops. At which station do they transfer? Answer with the "
                             f"station name exactly as printed on the map.",
                             ans, "label"),
                    dict(origin=o, dest=d, trips=trips[:10], normal_answer=sorted(xs0)))
        if qtype == "accessible_route":
            acc = accessible_set(g, in_view)
            if o not in acc or d not in acc:
                raise NoValidQuestion
            best_a, trips_a = plan(g, in_view, sc, o, d, objective="transfers", access=acc)
            if best_a is None or not trips_a or best_a[0] < 1:
                raise NoValidQuestion
            seqs_a = {tuple(rn(l[0]) for l in t) for t in trips_a}
            if len(seqs_a) != 1:
                raise NoValidQuestion
            ans = list(next(iter(seqs_a)))
            # the accessibility symbols must matter: the unrestricted best trips differ
            if tuple(ans) in seqs:
                raise NoValidQuestion
            # and the service change must matter: the accessible answer under NORMAL service differs
            _, trips_n = plan(g, in_view, None, o, d, objective="transfers", access=acc)
            seqs_n = {tuple(rn(l[0]) for l in t) for t in trips_n}
            if level >= 2 and tuple(ans) in seqs_n:
                raise NoValidQuestion
            return (Question("accessible_route",
                             f"A rider who uses a wheelchair travels {when} from {label[o]} to {label[d]} using only "
                             f"the services and free transfers shown on this map. Walking between stations joined on "
                             f"the map counts as a transfer, and the trip ends when a train arrives at {label[d]} "
                             f"itself. They can only enter, leave or "
                             f"change trains at stations marked with the accessibility symbol. They want the fewest "
                             f"transfers and, among those trips, the fewest station stops. Which services do they "
                             f"ride, in order? If more than one service runs between the same two stations on a leg, "
                             f"any of them is accepted. Answer as a JSON list of route letters or numbers, for example "
                             f"[\"A\", \"7\"].",
                             ans, "sequence"),
                    dict(origin=o, dest=d, trips=trips_a[:10], unrestricted_answer=sorted(seqs),
                         normal_answer=sorted(seqs_n),
                         accepted_answers=[list(x) for x in equivalent_sequences(g, in_view, sc, trips_a, acc)]))
        raise ValueError(qtype)

    def render(self, data, png_path):
        return render_map(self.graph, png_path, data["region"], data["style"],
                          service_change=data["service_change"])
