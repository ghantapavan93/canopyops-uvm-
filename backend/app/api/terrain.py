"""3D terrain awareness — a synthetic digital elevation model (DEM).

We can't legally pull a client's real LiDAR/DEM, so the terrain is generated
deterministically (a ridge + two hills + a gentle regional slope) over the
synthetic sandbox. Two surfaces:

  * ``GET /api/geo/terrain`` — the elevation grid, rendered as an interactive 3D
    mesh on the front end;
  * ``POST /api/geo/terrain/profile`` — the elevation/slope profile along a
    corridor centerline, so a planner can see access difficulty and steep
    sections (which is what the steep-slope constraint and crew safety turn on).

Deterministic + content-addressed ETag, so a device caches it for offline use.
"""
from __future__ import annotations

import hashlib
import math

from fastapi import APIRouter, Header, Response
from fastapi.responses import JSONResponse

from app.schemas import (
    TerrainGrid,
    TerrainProfileIn,
    TerrainProfileOut,
    TerrainProfilePoint,
)

router = APIRouter(tags=["terrain"])

# Sandbox terrain extent (matches the seed grid / district choropleth).
LON0, LAT0 = -83.20, 40.10
WIDTH, HEIGHT = 0.12, 0.06
STEEP_PCT = 30.0


def elevation(lon: float, lat: float) -> float:
    """Smooth, deterministic ground elevation (metres) — no randomness."""
    u = (lon - LON0) / WIDTH   # 0..1 west→east
    v = (lat - LAT0) / HEIGHT  # 0..1 south→north
    base = 235.0
    # A curving ridge running roughly W–E.
    ridge = 95.0 * math.exp(-(((v - 0.55 - 0.15 * math.sin(u * 3.14159)) ** 2) / 0.02))
    hill1 = 60.0 * math.exp(-(((u - 0.30) ** 2) / 0.020 + ((v - 0.30) ** 2) / 0.020))
    hill2 = 48.0 * math.exp(-(((u - 0.76) ** 2) / 0.015 + ((v - 0.72) ** 2) / 0.020))
    regional = 42.0 * u        # gentle rise to the east
    return round(base + ridge + hill1 + hill2 + regional, 1)


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    p = math.pi / 180.0
    x = (lon2 - lon1) * p * math.cos((lat1 + lat2) / 2 * p)
    y = (lat2 - lat1) * p
    return math.sqrt(x * x + y * y) * r


@router.get("/geo/terrain")
def terrain(cols: int = 56, rows: int = 36, if_none_match: str | None = Header(None)) -> Response:
    cols = min(max(cols, 8), 96)
    rows = min(max(rows, 8), 72)
    grid: list[list[float]] = []
    mn, mx = math.inf, -math.inf
    for r in range(rows):
        lat = LAT0 + HEIGHT * (r / (rows - 1))
        line: list[float] = []
        for c in range(cols):
            lon = LON0 + WIDTH * (c / (cols - 1))
            e = elevation(lon, lat)
            line.append(e)
            mn, mx = min(mn, e), max(mx, e)
        grid.append(line)

    etag = f'W/"terrain-{cols}x{rows}"'  # deterministic → content-addressed
    if if_none_match and if_none_match.strip() == etag:
        return Response(status_code=304, headers={"ETag": etag})
    body = TerrainGrid(
        bbox=[LON0, LAT0, LON0 + WIDTH, LAT0 + HEIGHT], cols=cols, rows=rows,
        min_elev=round(mn, 1), max_elev=round(mx, 1), elevations=grid,
    ).model_dump(by_alias=True)
    return JSONResponse(body, headers={"ETag": etag, "Cache-Control": "no-cache"})


@router.post("/geo/terrain/profile", response_model=TerrainProfileOut)
def terrain_profile(payload: TerrainProfileIn) -> TerrainProfileOut:
    """Sample elevation + slope evenly along a LineString (a corridor centerline)."""
    coords = [(float(p[0]), float(p[1])) for p in payload.geometry.get("coordinates", [])]
    if len(coords) < 2:
        return TerrainProfileOut(points=[], length_m=0, gain_m=0, max_slope_pct=0, steep_sections=0)

    # Cumulative length so we can resample at equal spacing.
    cum = [0.0]
    for i in range(1, len(coords)):
        cum.append(cum[-1] + _haversine_m(*coords[i - 1], *coords[i]))
    total = cum[-1]

    def at(dist: float) -> tuple[float, float]:
        for i in range(1, len(coords)):
            if dist <= cum[i] or i == len(coords) - 1:
                seg = cum[i] - cum[i - 1] or 1.0
                t = max(0.0, min(1.0, (dist - cum[i - 1]) / seg))
                lon = coords[i - 1][0] + t * (coords[i][0] - coords[i - 1][0])
                lat = coords[i - 1][1] + t * (coords[i][1] - coords[i - 1][1])
                return lon, lat
        return coords[-1]

    n = min(max(payload.samples, 2), 200)
    points: list[TerrainProfilePoint] = []
    gain = 0.0
    max_slope = 0.0
    steep = 0
    prev_e: float | None = None
    for k in range(n):
        dist = total * (k / (n - 1))
        lon, lat = at(dist)
        e = elevation(lon, lat)
        slope = 0.0
        if prev_e is not None:
            step = total / (n - 1) or 1.0
            slope = abs(e - prev_e) / step * 100.0
            if e > prev_e:
                gain += e - prev_e
            max_slope = max(max_slope, slope)
            if slope >= STEEP_PCT:
                steep += 1
        points.append(TerrainProfilePoint(
            distance_m=round(dist, 1), elevation_m=e, slope_pct=round(slope, 1)))
        prev_e = e

    return TerrainProfileOut(
        points=points, length_m=round(total, 1), gain_m=round(gain, 1),
        max_slope_pct=round(max_slope, 1), steep_sections=steep,
    )
