"""Geometry helpers in generator/families/subway/layout.py."""
from __future__ import annotations

import math

import numpy as np
import pytest

from generator.families.subway.layout import idw_warp, octi_path, octilinear_relax, offset_polyline, simplify


def octilinear(p, q, tol=1e-9):
    dx, dy = q[0] - p[0], q[1] - p[1]
    return abs(dx) < tol or abs(dy) < tol or abs(abs(dx) - abs(dy)) < tol


@pytest.mark.parametrize("seed", range(5))
def test_octi_path_segments_are_octilinear(seed):
    rng = np.random.default_rng(seed)
    for _ in range(200):
        a, b = tuple(rng.uniform(-5, 5, 2)), tuple(rng.uniform(-5, 5, 2))
        p = octi_path(a, b)
        assert p[0] == a and p[-1] == b and len(p) in (2, 4)
        assert all(octilinear(u, v, 1e-5) for u, v in zip(p, p[1:]))


def test_octi_path_special_cases():
    assert octi_path((0, 0), (3, 0)) == [(0, 0), (3, 0)]
    assert octi_path((0, 0), (2, -2)) == [(0, 0), (2, -2)]
    p = octi_path((0, 0), (4, 1))
    assert len(p) == 4 and all(octilinear(u, v) for u, v in zip(p, p[1:]))
    assert p[1][1] == 0 and p[2][1] == 1                     # straight in, 45 degrees in the middle, straight out


def test_offset_polyline_keeps_vertices_and_distance():
    pts = [(0, 0), (2, 0), (3, 1), (3, 4)]
    for off in (0.3, -0.3):
        o = offset_polyline(pts, off)
        assert o.shape == (len(pts), 2)
        assert np.allclose(o[0], [0, off])                    # left normal of +x is +y
        assert np.allclose(o[-1], [3 - off, 4])
    assert np.array_equal(offset_polyline(pts, 0), np.asarray(pts, float))


def test_offset_polyline_straight_line_is_translation():
    pts = np.array([(0, 0), (1, 1), (2, 2), (5, 5)], float)
    o = offset_polyline(pts, 1.0)
    d = (o - pts)
    assert np.allclose(d, d[0]) and math.isclose(np.hypot(*d[0]), 1.0)


def test_simplify_keeps_endpoints_and_subset():
    x = np.linspace(0, 10, 200)
    pts = np.stack([x, np.sin(x) * 0.01], 1)
    s = simplify(pts, 0.05)
    assert np.array_equal(s[0], pts[0]) and np.array_equal(s[-1], pts[-1]) and len(s) == 2
    corner = np.array([(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)], float)
    assert np.array_equal(simplify(corner, 1e-6), corner[[0, 2, 4]])


def test_idw_warp_moves_sources_to_destinations():
    src = np.array([[0, 0], [5, 0], [0, 5]], float)
    dst = src + np.array([[1, 0], [0, 1], [-1, -1]], float)
    out = idw_warp(src, src, dst, eps=1e-6)
    assert np.allclose(out, dst, atol=1e-6)


def test_octilinear_relax_is_deterministic_and_straightens():
    rng = np.random.default_rng(0)
    pos = rng.uniform(0, 3, (8, 2))
    edges = [(i, i + 1) for i in range(7)]
    a = octilinear_relax(pos, edges, [], iters=300)
    b = octilinear_relax(pos, edges, [], iters=300)
    assert np.array_equal(a, b)

    def err(p):
        th = np.array([math.atan2(*(p[j] - p[i])[::-1]) for i, j in edges])
        return np.abs(th - np.round(th / (np.pi / 4)) * (np.pi / 4)).mean()
    assert err(a) < err(pos) * 0.75          # anchor + min spacing pull against it, so not to zero
