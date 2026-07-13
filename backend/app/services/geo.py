"""Geometry helpers: PostGIS/GeoAlchemy2 <-> GeoJSON, and spatial math.

Read-path conversions use shapely; heavy spatial filtering stays in PostGIS
(see the treatments query) rather than pulling every feature into Python.
"""
from __future__ import annotations

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping, shape


def to_geojson(geom) -> dict | None:
    """GeoAlchemy2 element -> GeoJSON geometry dict (EPSG:4326)."""
    if geom is None:
        return None
    return mapping(to_shape(geom))


def to_shape_or_none(geom):
    """GeoAlchemy2 element -> shapely geometry (or None)."""
    return None if geom is None else to_shape(geom)


def coverage_ratio(planned, actual) -> float | None:
    """Fraction of the planned polygon actually covered by execution geometry.

    This is the front-line 'planned vs. actual' signal: a value < 1.0 means part
    of the planned area was not treated (partial coverage), which must keep the
    record visibly incomplete.
    """
    if planned is None or actual is None:
        return None
    p = to_shape(planned)
    a = to_shape(actual)
    if p.area == 0:
        return None
    covered = p.intersection(a).area
    return round(min(covered / p.area, 1.0), 4)


def geojson_to_wkt(geojson: dict) -> str:
    """GeoJSON geometry dict -> WKT for insertion via ST_GeomFromText."""
    return shape(geojson).wkt
