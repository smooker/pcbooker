"""
isolation.py — Generate isolation toolpaths from copper polygons

Uses Shapely buffer() for polygon offset operations.
Outline = expand outward (laser cuts outside copper)
Inline = shrink inward (laser cuts inside copper boundary)
"""

from shapely.geometry import Polygon, MultiPolygon, MultiLineString
from shapely.ops import unary_union


def generate_isolation(geometry, offset_mm, mode='outline', resolution=32):
    """
    Generate isolation path around/inside geometry.

    Args:
        geometry: Shapely Polygon or MultiPolygon (copper areas)
        offset_mm: offset distance in mm (tool radius + clearance)
        mode: 'outline' (expand outward) or 'inline' (shrink inward)
        resolution: segments per quarter circle for smooth curves

    Returns:
        Shapely geometry representing the isolation path boundary
    """
    if offset_mm <= 0:
        return geometry

    if mode == 'outline':
        buffered = geometry.buffer(offset_mm, resolution=resolution)
    elif mode == 'inline':
        buffered = geometry.buffer(-offset_mm, resolution=resolution)
    else:
        raise ValueError(f"Unknown mode: {mode}. Use 'outline' or 'inline'.")

    if buffered.is_empty:
        return None

    return buffered


def isolation_paths(geometry, offset_mm, mode='outline', resolution=32):
    """
    Extract just the boundary lines from isolation result.
    These are the actual paths the laser will follow.

    Returns:
        list of Shapely LineString objects
    """
    result = generate_isolation(geometry, offset_mm, mode, resolution)
    if result is None:
        return []

    paths = []
    if isinstance(result, Polygon):
        paths.append(result.exterior)
        for interior in result.interiors:
            paths.append(interior)
    elif isinstance(result, MultiPolygon):
        for poly in result.geoms:
            paths.append(poly.exterior)
            for interior in poly.interiors:
                paths.append(interior)

    return paths


def multi_pass_isolation(geometry, offset_mm, passes=1, overlap_mm=0.0,
                         mode='outline', resolution=32):
    """
    Generate multiple isolation passes with overlap.

    Args:
        geometry: copper geometry
        offset_mm: base offset for first pass
        passes: number of passes
        overlap_mm: overlap between passes (0 = no overlap)
        mode: 'outline' or 'inline'
        resolution: curve smoothness

    Returns:
        list of lists of LineString paths (one list per pass)
    """
    all_passes = []
    for i in range(passes):
        current_offset = offset_mm + i * (offset_mm - overlap_mm)
        paths = isolation_paths(geometry, current_offset, mode, resolution)
        if paths:
            all_passes.append(paths)

    return all_passes
