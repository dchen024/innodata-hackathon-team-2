"""Service-change semantics in the planner's network() and in the rendered layout."""
from __future__ import annotations

from collections import defaultdict

from generator.families.subway.family import _bfs_path, network
from validate.families.subway import graph


def _cases(generated, built_set, kind):
    import json
    out = [t["data"] for t in generated if (t["data"]["service_change"] or {}).get("kind") == kind]
    for r in built_set["records"]:
        data = json.loads((built_set["dir"] / r["data"]).read_text())
        if (data["service_change"] or {}).get("kind") == kind:
            out.append(data)
    return out


def test_suspension_removes_stops_inside_stretch(generated, built_set):
    g = graph()
    cases = _cases(generated, built_set, "suspend")
    assert len(cases) >= 5
    for data in cases:
        sc, iv, lay = data["service_change"], set(data["stations_in_view"]), data["layout"]
        stops0, ride0 = network(g, iv)
        stops, ride = network(g, iv, sc)
        for r in sc["routes"]:
            adj = defaultdict(set)
            for a, b in ride0[r]:
                adj[a].add(b)
                adj[b].add(a)
            path = _bfs_path(adj, sc["from"], sc["to"])
            assert path and len(path) >= 3, (data["seed"], r)
            for s in path[1:-1]:
                assert r in stops0[s]
                assert r not in stops[s], (data["seed"], r, s)
                assert r not in lay["stations"][s]["stops"], (data["seed"], r, s)
                assert [s, r] in lay["no_stop"]
            for u, v in zip(path, path[1:]):
                assert tuple(sorted((u, v))) not in {tuple(sorted(e)) for e in ride[r]}
            assert any(x[0] == r for x in lay["suspended"])
        # a notice is printed and names the stretch
        assert g["stations"][sc["from"]]["name"] in sc["notice"][0]
        assert g["stations"][sc["to"]]["name"] in sc["notice"][0]


def test_skip_closes_station_but_trains_run_through(generated, built_set):
    g = graph()
    cases = _cases(generated, built_set, "skip")
    assert cases
    for data in cases:
        sc, iv, lay = data["service_change"], set(data["stations_in_view"]), data["layout"]
        x = sc["station"]
        stops0, ride0 = network(g, iv)
        stops, ride = network(g, iv, sc)
        for r in sc["routes"]:
            assert r not in stops[x] and r not in lay["stations"][x]["stops"]
            nb = sorted({b if a == x else a for a, b in ride0[r] if x in (a, b)})
            if len(nb) == 2 and all(n in iv for n in nb):
                assert tuple(nb) in {tuple(sorted(e)) for e in ride[r]}, "neighbours must become consecutive"


def test_no_service_change_is_identity():
    g = graph()
    iv = set(list(g["stations"])[:80])
    assert network(g, iv) == network(g, iv, None) == network(g, iv, {})
