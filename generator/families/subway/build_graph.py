"""Build the NYC subway graph from the MTA's public GTFS feed and station list.

Inputs (downloaded by `fetch()`, kept out of git in data/raw/):
    GTFS static subway feed  https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip
    MTA Subway Stations      https://data.ny.gov/resource/39hk-dx4f.csv   (complex IDs, borough, structure)

Output: data/subway_graph.json
    routes      {route_id: {name, long_name, color, text_color, express}}
    stations    {stop_id: {name, lat, lon, complex_id, borough, structure, routes}}
    ride_edges  [{route, a, b, minutes, km, trips}]   consecutive weekday-daytime stops; minutes = median run time
    transfers   [{a, b, minutes}]                      walking transfers between different stations of one complex

Run:  python -m generator.families.subway.build_graph
"""
from __future__ import annotations

import csv
import io
import json
import math
import statistics
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "subway_graph.json"
OUT_WEEKEND = ROOT / "data" / "subway_graph_saturday.json"
GTFS_URL = "https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip"
STATIONS_URL = "https://data.ny.gov/resource/39hk-dx4f.csv?$limit=5000"

SKIP_ROUTES = {"FX", "6X", "7X", "SI"}     # rush-hour express variants and Staten Island Railway
DAY_START, DAY_END = 7 * 3600, 19 * 3600   # weekday daytime window for run times
MIN_SHARE = 0.10                           # a stop pair must appear in >=10% of a route's trips (drops rare reroutes)


def fetch():
    RAW.mkdir(parents=True, exist_ok=True)
    for url, name in ((GTFS_URL, "gtfs_subway.zip"), (STATIONS_URL, "mta_subway_stations.csv")):
        path = RAW / name
        if not path.exists():
            print(f"downloading {url}")
            urllib.request.urlretrieve(url, path)


def _rows(zf, name):
    with zf.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))


def _secs(t):
    h, m, s = map(int, t.split(":"))
    return h * 3600 + m * 60 + s


def haversine_km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def build(service: str = "Weekday", out: Path = OUT):
    fetch()
    zf = zipfile.ZipFile(RAW / "gtfs_subway.zip")
    feed_info = next(_rows(zf, "feed_info.txt"), {})

    routes = {}
    for r in _rows(zf, "routes.txt"):
        if r["route_id"] in SKIP_ROUTES:
            continue
        routes[r["route_id"]] = dict(name=r["route_short_name"], long_name=r["route_long_name"],
                                     color="#" + (r["route_color"] or "808183"),
                                     text_color="#" + (r["route_text_color"] or "FFFFFF"),
                                     express="Express" in r["route_long_name"])

    parent = {}
    stations = {}
    for s in _rows(zf, "stops.txt"):
        if s["location_type"] == "1":
            stations[s["stop_id"]] = dict(name=s["stop_name"], lat=float(s["stop_lat"]), lon=float(s["stop_lon"]))
        else:
            parent[s["stop_id"]] = s["parent_station"] or s["stop_id"]

    with open(RAW / "mta_subway_stations.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            st = stations.get(r["gtfs_stop_id"])
            if st:
                st.update(complex_id=r["complex_id"], borough=r["borough"], structure=r["structure"],
                          ada=int(float(r["ada"] or 0)),       # 1 = fully accessible, 2 = partially, 0 = not
                          daytime_routes=r["daytime_routes"].split())

    trips = {t["trip_id"]: t["route_id"] for t in _rows(zf, "trips.txt")
             if t["service_id"] == service and t["route_id"] in routes}

    # walk stop_times trip by trip (the file is grouped by trip)
    run_times = defaultdict(list)            # (route, a, b) sorted pair -> [seconds]
    stop_trips = defaultdict(lambda: defaultdict(int))   # route -> station -> daytime trips that stop there
    pair_trips = defaultdict(int)
    route_trips = Counter()
    cur, seq = None, []

    def flush(trip_id, stops):
        if not stops:
            return
        stops.sort()
        if not (DAY_START <= stops[0][1] <= DAY_END):
            return
        route = trips[trip_id]
        route_trips[route] += 1
        for st_ in {x[2] for x in stops}:
            stop_trips[route][st_] += 1
        for (_, dep, a, _), (_, _, b, arr) in zip(stops, stops[1:]):
            if a == b:
                continue
            key = (route, *sorted((a, b)))
            run_times[key].append(arr - dep)
            pair_trips[key] += 1

    for st in _rows(zf, "stop_times.txt"):
        tid = st["trip_id"]
        if tid != cur:
            if cur in trips:
                flush(cur, seq)
            cur, seq = tid, []
        if tid in trips:
            seq.append((int(st["stop_sequence"]), _secs(st["departure_time"]),
                        parent[st["stop_id"]], _secs(st["arrival_time"])))
    if cur in trips:
        flush(cur, seq)

    ride_edges = []
    served = defaultdict(set)
    for (route, a, b), secs in sorted(run_times.items()):
        if pair_trips[(route, a, b)] < MIN_SHARE * route_trips[route]:
            continue
        sa, sb = stations[a], stations[b]
        ride_edges.append(dict(route=route, a=a, b=b, minutes=round(statistics.median(secs) / 60, 1),
                               km=round(haversine_km(sa["lat"], sa["lon"], sb["lat"], sb["lon"]), 2),
                               trips=pair_trips[(route, a, b)]))
        served[a].add(route)
        served[b].add(route)

    transfers = []
    seen = set()
    for t in _rows(zf, "transfers.txt"):
        a, b = t["from_stop_id"], t["to_stop_id"]
        if a == b or a not in served or b not in served:
            continue
        key = tuple(sorted((a, b)))
        if key in seen:
            continue
        seen.add(key)
        transfers.append(dict(a=key[0], b=key[1], minutes=round(int(t["min_transfer_time"] or 180) / 60, 1)))

    stations = {sid: {**s, "routes": sorted(served[sid], key=lambda r: list(routes).index(r))}
                for sid, s in stations.items() if sid in served}
    graph = dict(
        source=dict(gtfs=GTFS_URL, stations=STATIONS_URL, feed_version=feed_info.get("feed_version"),
                    feed_start=feed_info.get("feed_start_date"), feed_end=feed_info.get("feed_end_date"),
                    service=f"{service} trips starting 07:00-19:00; run time = median departure->next arrival"),
        routes={r: v for r, v in routes.items() if any(e["route"] == r for e in ride_edges)},
        stations=stations, ride_edges=ride_edges, transfers=transfers,
        stop_trips={r: dict(v) for r, v in stop_trips.items() if r in routes})
    out.write_text(json.dumps(graph, indent=1))
    print(f"wrote {out.relative_to(ROOT)}: {len(graph['routes'])} routes, {len(stations)} stations, "
          f"{len(ride_edges)} ride edges, {len(transfers)} transfers")
    return graph


if __name__ == "__main__":
    build("Weekday", OUT)
    build("Saturday", OUT_WEEKEND)
