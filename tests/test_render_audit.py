"""Render audit on the fixed 'midtown' region: no colliding markers or labels, every station in view printed."""
from __future__ import annotations

import pytest
from PIL import Image

from generator.families.subway.render import complex_groups, load_graph, render_map


@pytest.fixture(scope="module", params=[("weekday", "clean"), ("saturday", "print")])
def midtown(request, tmp_path_factory):
    svc, style = request.param
    g = load_graph(svc)
    png = tmp_path_factory.mktemp("midtown") / f"{svc}_{style}.png"
    return g, render_map(g, str(png), "midtown", style), png


def test_no_marker_or_label_collisions(midtown):
    _, lay, _ = midtown
    kinds = {o["kind"] for o in lay["overlaps"]}
    assert not kinds & {"marker/marker", "label/label", "label/marker"}, lay["overlaps"]


def test_every_station_in_view_is_drawn_and_labelled(midtown):
    g, lay, _ = midtown
    S = g["stations"]
    assert len(lay["stations_in_view"]) >= 40
    assert lay["unlabelled"] == []
    assert set(lay["labels"]) == set(lay["stations_in_view"]) == set(lay["stations"])
    groups = complex_groups(g, set(lay["stations_in_view"]))
    for s, lab in lay["labels"].items():
        # a label prints the name of the station itself or of a station in the same transfer complex
        names = {S[m]["name"] for G in groups.values() if s in G for m in G} | {S[s]["name"]}
        assert lab["text"] in names, (s, lab["text"])


def test_label_boxes_inside_image(midtown):
    _, lay, png = midtown
    w, h = Image.open(png).size
    for lab in lay["labels"].values():
        x0, y0, x1, y1 = lab["bbox_px"]
        assert 0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h


def test_every_stop_chip_is_a_route_that_stops(midtown):
    g, lay, _ = midtown
    from generator.families.subway.family import network
    stops, _ = network(g, set(lay["stations_in_view"]))
    for s, v in lay["stations"].items():
        assert set(v["stops"]) == stops[s], g["stations"][s]["name"]
        assert not set(v["passes"]) & set(v["stops"])
