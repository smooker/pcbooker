"""
gerber_loader.py — Load Gerber files and convert to Shapely geometry

Uses gerbonara for parsing, converts graphic objects to Shapely polygons
for isolation routing and visualization.
"""

import os
from pathlib import Path

from gerbonara import LayerStack, GerberFile
from gerbonara.graphic_objects import Line, Arc, Flash, Region
from gerbonara.apertures import CircleAperture, RectangleAperture, ObroundAperture
from shapely.geometry import (
    Point, LineString, Polygon, MultiPolygon, box
)
from shapely.ops import unary_union
import shapely
import math


def load_board(directory):
    """
    Load all Gerber files from a directory.

    Returns:
        dict of {layer_name: GerberFile}
    """
    stack = LayerStack.open(directory)
    layers = {}

    # Extract named layers from the stack
    for side in ('top', 'bottom'):
        for role in ('copper', 'mask', 'silk', 'paste'):
            layer = getattr(stack, f'{side}_{role}', None)
            if layer is not None:
                layers[f'{side}_{role}'] = layer

    if stack.outline is not None:
        layers['outline'] = stack.outline

    # Also check for drill files
    if hasattr(stack, 'drills') and stack.drills:
        for i, drill in enumerate(stack.drills):
            layers[f'drill_{i}'] = drill

    return layers


def load_single(filepath):
    """Load a single Gerber file."""
    return GerberFile.open(filepath)


def load_gerber_files(filepaths):
    """
    Load multiple individual Gerber files by path.

    Returns:
        dict of {filename: GerberFile}
    """
    layers = {}
    for fp in filepaths:
        name = Path(fp).stem
        try:
            layers[name] = GerberFile.open(fp)
        except Exception as e:
            print(f"Warning: Could not load {fp}: {e}")
    return layers


def _aperture_radius(aperture):
    """Get effective radius of an aperture in mm."""
    if isinstance(aperture, CircleAperture):
        return float(aperture.diameter) / 2.0
    elif isinstance(aperture, RectangleAperture):
        return max(float(aperture.w), float(aperture.h)) / 2.0
    elif isinstance(aperture, ObroundAperture):
        return max(float(aperture.w), float(aperture.h)) / 2.0
    else:
        return 0.1  # fallback 0.1mm


def _obj_to_mm(obj, unit):
    """Convert object coordinates to mm."""
    if unit == 'inch':
        return lambda v: float(v) * 25.4
    return lambda v: float(v)


def flash_to_shapely(flash, to_mm):
    """Convert a Flash object to Shapely geometry."""
    x = to_mm(flash.x)
    y = to_mm(flash.y)
    r = _aperture_radius(flash.aperture)
    if isinstance(flash.aperture, CircleAperture):
        return Point(x, y).buffer(r, resolution=16)
    elif isinstance(flash.aperture, (RectangleAperture, ObroundAperture)):
        w = to_mm(flash.aperture.w) if hasattr(flash.aperture, 'w') else r * 2
        h = to_mm(flash.aperture.h) if hasattr(flash.aperture, 'h') else r * 2
        return box(x - w/2, y - h/2, x + w/2, y + h/2)
    else:
        return Point(x, y).buffer(r, resolution=16)


def line_to_shapely(line, to_mm):
    """Convert a Line object to Shapely geometry."""
    x1, y1 = to_mm(line.x1), to_mm(line.y1)
    x2, y2 = to_mm(line.x2), to_mm(line.y2)
    r = _aperture_radius(line.aperture)
    ls = LineString([(x1, y1), (x2, y2)])
    if r > 0:
        return ls.buffer(r, cap_style='round', join_style='round')
    return ls


def arc_to_shapely(arc, to_mm, segments=32):
    """Convert an Arc object to Shapely geometry (discretized)."""
    cx = to_mm(arc.cx) if hasattr(arc, 'cx') else 0
    cy = to_mm(arc.cy) if hasattr(arc, 'cy') else 0
    x1, y1 = to_mm(arc.x1), to_mm(arc.y1)
    x2, y2 = to_mm(arc.x2), to_mm(arc.y2)

    # Calculate arc points
    r = math.sqrt((x1 - cx)**2 + (y1 - cy)**2)
    if r < 1e-6:
        return LineString([(x1, y1), (x2, y2)])

    start_angle = math.atan2(y1 - cy, x1 - cx)
    end_angle = math.atan2(y2 - cy, x2 - cx)

    clockwise = getattr(arc, 'clockwise', False)
    if clockwise:
        if end_angle >= start_angle:
            end_angle -= 2 * math.pi
    else:
        if end_angle <= start_angle:
            end_angle += 2 * math.pi

    angle_span = end_angle - start_angle
    n_points = max(int(abs(angle_span) / (2 * math.pi) * segments), 2)

    points = []
    for i in range(n_points + 1):
        t = start_angle + angle_span * i / n_points
        px = cx + r * math.cos(t)
        py = cy + r * math.sin(t)
        points.append((px, py))

    ls = LineString(points)
    ap_r = _aperture_radius(arc.aperture) if hasattr(arc, 'aperture') and arc.aperture else 0
    if ap_r > 0:
        return ls.buffer(ap_r, cap_style='round')
    return ls


def region_to_shapely(region, to_mm):
    """Convert a Region object to Shapely Polygon."""
    coords = []
    for obj in region.objs:
        if isinstance(obj, Line):
            coords.append((to_mm(obj.x1), to_mm(obj.y1)))
            coords.append((to_mm(obj.x2), to_mm(obj.y2)))
        elif isinstance(obj, Arc):
            # Discretize arc
            x1, y1 = to_mm(obj.x1), to_mm(obj.y1)
            coords.append((x1, y1))
            x2, y2 = to_mm(obj.x2), to_mm(obj.y2)
            coords.append((x2, y2))

    if len(coords) >= 3:
        try:
            poly = Polygon(coords)
            if poly.is_valid:
                return poly
            return poly.buffer(0)  # fix invalid geometry
        except Exception:
            return None
    return None


def layer_to_polygons(layer):
    """
    Convert a GerberFile layer to list of Shapely geometries.

    Handles: Flash, Line, Arc, Region objects.
    All coordinates converted to mm.

    Returns:
        list of Shapely geometry objects
    """
    unit = getattr(layer, 'unit', None)
    if unit and str(unit).lower().startswith('inch'):
        to_mm = lambda v: float(v) * 25.4
    else:
        to_mm = lambda v: float(v)

    geometries = []

    for obj in layer.objects:
        try:
            if isinstance(obj, Flash):
                geom = flash_to_shapely(obj, to_mm)
            elif isinstance(obj, Line):
                geom = line_to_shapely(obj, to_mm)
            elif isinstance(obj, Arc):
                geom = arc_to_shapely(obj, to_mm)
            elif isinstance(obj, Region):
                geom = region_to_shapely(obj, to_mm)
            else:
                continue

            if geom is not None and not geom.is_empty:
                geometries.append(geom)
        except Exception as e:
            print(f"Warning: skipping object {type(obj).__name__}: {e}")

    return geometries


def layer_to_merged(layer):
    """
    Convert layer to a single merged Shapely geometry (union of all objects).
    Useful for isolation routing on copper layers.
    """
    polygons = layer_to_polygons(layer)
    if not polygons:
        return None
    try:
        return unary_union(polygons)
    except Exception as e:
        print(f"Warning: union failed: {e}")
        return None
