"""
hatch.py — raster (hatch) fill: parallel lines over an area, for HPGL export.

The TRUMPF VectorMark is a vector laser, so "raster" here means hatching: the area to
ablate is filled with parallel lines one beam width apart. The lines come back in
serpentine order (every other row reversed), so the travel between rows is short.
"""

import math

from shapely import affinity
from shapely.geometry import LineString, box


def _row_segments(region, y, x0, x1):
    """The pieces of the horizontal line at y that lie inside region, left to right."""
    cut = LineString([(x0, y), (x1, y)]).intersection(region)
    parts = getattr(cut, 'geoms', [cut])
    segs = [p for p in parts if isinstance(p, LineString) and p.length > 0]
    segs = [s if s.coords[0][0] <= s.coords[-1][0] else LineString(s.coords[::-1]) for s in segs]
    return sorted(segs, key=lambda s: s.coords[0][0])


def _hatch_one(region, pitch_mm, angle_deg):
    # rotate the region so the hatch is horizontal, hatch, rotate the lines back
    r = affinity.rotate(region, -angle_deg, origin=(0, 0)) if angle_deg else region
    minx, miny, maxx, maxy = r.bounds
    lines = []
    row = 0
    y = miny + pitch_mm / 2  # half a pitch in from the edge, so the rows are centred
    while y < maxy:
        segs = _row_segments(r, y, minx - 1, maxx + 1)
        if row % 2:
            segs = [LineString(s.coords[::-1]) for s in reversed(segs)]
        lines.extend(segs)
        if segs:
            row += 1
        y += pitch_mm
    if angle_deg:
        lines = [affinity.rotate(l, angle_deg, origin=(0, 0)) for l in lines]
    return lines


def hatch_lines(region, pitch_mm, angle_deg=0.0, cross=False):
    """
    Fill region with parallel lines.

    Args:
        region: Shapely Polygon/MultiPolygon to fill (mm)
        pitch_mm: distance between lines (about the beam width)
        angle_deg: line direction, 0 = along X
        cross: add a second pass at angle_deg + 90

    Returns:
        list of LineString, serpentine order
    """
    if not pitch_mm or pitch_mm <= 0 or math.isnan(pitch_mm):
        raise ValueError(f"pitch_mm must be > 0, got {pitch_mm}")
    if region is None or region.is_empty:
        return []
    lines = _hatch_one(region, pitch_mm, angle_deg)
    if cross:
        lines += _hatch_one(region, pitch_mm, angle_deg + 90)
    return lines


def ablate_region(copper, offset_mm, board=None, margin_mm=1.0):
    """
    The area to burn away: the board minus the copper grown by offset_mm.

    Args:
        copper: merged copper geometry (mm)
        offset_mm: clearance kept around the copper (as for isolation)
        board: board outline polygon; None = copper bounding box + margin_mm
        margin_mm: margin around the copper when there is no board outline
    """
    if board is None:
        minx, miny, maxx, maxy = copper.bounds
        board = box(minx - margin_mm, miny - margin_mm, maxx + margin_mm, maxy + margin_mm)
    keep = copper.buffer(offset_mm) if offset_mm > 0 else copper
    return board.difference(keep)
