"""Schematic (octilinear) layout computed from real station coordinates.

1. Project stations to a local km grid.
2. Relax positions so every station-to-station link points close to a multiple of 45 degrees, while staying
   near the true geography and keeping a minimum spacing between stations.
3. Every link is then drawn as at most two octilinear legs (one 45-degree leg + one horizontal/vertical leg),
   so all drawn segments are exactly octilinear.
4. The shoreline is warped by the same displacement field (inverse-distance weighting) so land and lines agree.

This is our own algorithmic layout from open GTFS data; it does not trace any published map.
"""
from __future__ import annotations

import math

import numpy as np

KM_LAT = 110.57


def project(lat, lon, lat0, lon0):
    return ((np.asarray(lon) - lon0) * math.cos(math.radians(lat0)) * 111.32,
            (np.asarray(lat) - lat0) * KM_LAT)


def rotate(xy: np.ndarray, deg: float) -> np.ndarray:
    t = math.radians(deg)
    R = np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])
    return xy @ R.T


def octilinear_relax(pos: np.ndarray, edges: list[tuple[int, int]], links: list[tuple[int, int]],
                     iters: int = 600, min_sep: float = 0.32, anchor: float = 0.02, seed: int = 0,
                     link_len=None) -> np.ndarray:
    """pos: (n,2) km. edges: track links to make octilinear. links: transfer links to keep short."""
    p = pos.copy()
    g = pos.copy()
    E = np.array(edges, dtype=int).reshape(-1, 2)
    T = np.array(links, dtype=int).reshape(-1, 2)
    TL = np.full(len(T), 0.11) if link_len is None else np.asarray(link_len, float)
    for it in range(iters):
        step = 0.5 * (1 - it / iters) + 0.05
        d = p[E[:, 1]] - p[E[:, 0]]
        L = np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-6)
        th = np.arctan2(d[:, 1], d[:, 0])
        th_t = np.round(th / (np.pi / 4)) * (np.pi / 4)
        Lt = np.maximum(L, min_sep)
        tgt = np.stack([np.cos(th_t), np.sin(th_t)], 1) * Lt[:, None]
        corr = (tgt - d) * 0.5 * step
        np.add.at(p, E[:, 0], -corr)
        np.add.at(p, E[:, 1], corr)
        if len(T):
            dt = p[T[:, 1]] - p[T[:, 0]]
            lt = np.maximum(np.hypot(dt[:, 0], dt[:, 1]), 1e-6)
            # stations of one complex are drawn as one group: pull them to ~110 m apart (readability over geography)
            pull = dt * ((lt - TL) / lt)[:, None] * 0.35 * step
            # and line them up side by side (horizontal), like the transfer rows on the 2026 map
            align = np.zeros_like(dt)
            align[:, 1] = dt[:, 1] * 0.2 * step
            pull += align
            np.add.at(p, T[:, 0], pull)
            np.add.at(p, T[:, 1], -pull)
        # keep stations apart
        diff = p[:, None, :] - p[None, :, :]
        dist = np.hypot(diff[..., 0], diff[..., 1]) + np.eye(len(p))
        push = np.clip(min_sep - dist, 0, None) / dist
        np.fill_diagonal(push, 0)
        if len(T):
            push[T[:, 0], T[:, 1]] = 0      # stations of one complex may sit close together
            push[T[:, 1], T[:, 0]] = 0
        p += (diff * push[..., None]).sum(1) * 0.25 * step
        # stations keep clear of track they are not on (a line passing under a station's markers would
        # read as a stop): push the station off the segment, the segment the other way
        if it % 2 == 0 and it > iters // 5 and len(E):
            A_, B_ = p[E[:, 0]], p[E[:, 1]]
            AB = B_ - A_
            L2 = np.maximum((AB ** 2).sum(1), 1e-9)
            t_ = np.clip(((p[:, None, :] - A_[None]) * AB[None]).sum(-1) / L2[None], 0, 1)
            proj = A_[None] + t_[..., None] * AB[None]
            dv = p[:, None, :] - proj
            dd = np.hypot(dv[..., 0], dv[..., 1])
            own = (E[None, :, 0] == np.arange(len(p))[:, None]) | (E[None, :, 1] == np.arange(len(p))[:, None])
            clear = min_sep * 0.62
            bad = (dd < clear) & ~own & (t_ > 0.02) & (t_ < 0.98)
            if bad.any():
                ii, jj = np.nonzero(bad)
                push = dv[ii, jj] / np.maximum(dd[ii, jj], 1e-6)[:, None] * (clear - dd[ii, jj])[:, None] * 0.5
                np.add.at(p, ii, push)
                np.add.at(p, E[jj, 0], -push * 0.5)
                np.add.at(p, E[jj, 1], -push * 0.5)
        p += (g - p) * anchor
    return p


def octi_path(a, b):
    """Octilinear path from a to b: straight leg, 45-degree leg in the middle, straight leg.
    Lines therefore always enter and leave stations straight, so stop chips sit square across the bundle."""
    (xa, ya), (xb, yb) = a, b
    dx, dy = xb - xa, yb - ya
    m = min(abs(dx), abs(dy))
    if m < 1e-6 or abs(abs(dx) - abs(dy)) < 1e-6:
        return [a, b]
    sx, sy = math.copysign(1, dx), math.copysign(1, dy)
    if abs(dx) > abs(dy):
        h = (abs(dx) - m) / 2
        p1 = (xa + sx * h, ya)
        p2 = (p1[0] + sx * m, yb)
    else:
        h = (abs(dy) - m) / 2
        p1 = (xa, ya + sy * h)
        p2 = (xb, p1[1] + sy * m)
    return [a, p1, p2, b]


def offset_polyline(pts, off):
    """Offset a polyline to the left by `off` with mitred joins."""
    P = np.asarray(pts, float)
    if len(P) < 2 or off == 0:
        return P
    seg = P[1:] - P[:-1]
    n = np.stack([-seg[:, 1], seg[:, 0]], 1)
    n /= np.maximum(np.hypot(n[:, 0], n[:, 1]), 1e-9)[:, None]
    out = [P[0] + n[0] * off]
    for i in range(1, len(P) - 1):
        m = n[i - 1] + n[i]
        mn = np.hypot(*m)
        if mn < 1e-6:
            out.append(P[i] + n[i] * off)
            continue
        m /= mn
        cos = max(float(np.dot(m, n[i])), 0.3)
        out.append(P[i] + m * off / cos)
    out.append(P[-1] + n[-1] * off)
    return np.array(out)


def idw_warp(points: np.ndarray, src: np.ndarray, dst: np.ndarray, power: float = 2.0, eps: float = 0.05):
    """Move arbitrary points by the station displacement field (src -> dst)."""
    disp = dst - src
    out = np.empty_like(points)
    for i in range(0, len(points), 4000):
        q = points[i:i + 4000]
        d2 = ((q[:, None, :] - src[None, :, :]) ** 2).sum(-1) + eps ** 2
        w = 1.0 / d2 ** (power / 2)
        out[i:i + 4000] = q + (w[..., None] * disp[None]).sum(1) / w.sum(1)[:, None]
    return out


def simplify(coords: np.ndarray, tol: float) -> np.ndarray:
    """Douglas-Peucker polyline simplification."""
    if len(coords) < 3:
        return coords
    keep = np.zeros(len(coords), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(coords) - 1)]
    while stack:
        i, j = stack.pop()
        a, b = coords[i], coords[j]
        ab = b - a
        n = np.hypot(*ab)
        seg = coords[i + 1:j]
        if len(seg) == 0:
            continue
        if n < 1e-12:
            d = np.hypot(*(seg - a).T)
        else:
            d = np.abs(ab[0] * (seg[:, 1] - a[1]) - ab[1] * (seg[:, 0] - a[0])) / n
        k = int(np.argmax(d))
        if d[k] > tol:
            keep[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return coords[keep]
