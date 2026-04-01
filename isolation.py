"""
isolation.py — Generate isolation toolpaths from copper polygons

Uses Shapely buffer() for polygon offset operations.
Outline = expand outward (laser cuts outside copper)
Inline = shrink inward (laser cuts inside copper boundary)

Smart gap handling: merges near-overlapping paths to prevent
double laser burns in narrow gaps between traces.
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


def _extract_paths(geom):
    """Extract boundary paths (exterior + interior rings) from polygon geometry."""
    paths = []
    if geom is None or geom.is_empty:
        return paths

    polys = [geom] if isinstance(geom, Polygon) else list(geom.geoms)
    for poly in polys:
        paths.append(poly.exterior)
        for interior in poly.interiors:
            paths.append(interior)
    return paths


def isolation_paths(geometry, offset_mm, mode='outline',
                    min_gap_mm=0.0, resolution=32):
    """
    Extract boundary lines from isolation result.
    These are the actual paths the laser will follow.

    Args:
        geometry: copper geometry (merged)
        offset_mm: isolation offset in mm
        mode: 'outline' or 'inline'
        min_gap_mm: minimum gap between paths — narrower gaps get merged
                    to prevent double laser burns. 0 = no merging.
        resolution: curve smoothness

    Returns:
        list of Shapely LinearRing/LineString objects
    """
    result = generate_isolation(geometry, offset_mm, mode, resolution)
    if result is None:
        return []

    if min_gap_mm <= 0:
        return _extract_paths(result)

    # --- Smart gap merging ---

    # Step 1: merge buffered polygons that are closer than min_gap_mm
    # buffer-out-then-in closes narrow gaps between separate polygons
    merged = result.buffer(min_gap_mm / 2).buffer(-min_gap_mm / 2)
    if merged is None or merged.is_empty:
        return _extract_paths(result)

    # Step 2: remove interior holes narrower than min_gap_mm
    # (these would cause two parallel paths very close together)
    polys = [merged] if isinstance(merged, Polygon) else list(merged.geoms)
    cleaned = []
    for poly in polys:
        keep_interiors = []
        for interior in poly.interiors:
            hole = Polygon(interior)
            shrunk = hole.buffer(-min_gap_mm / 2)
            if not shrunk.is_empty:
                # Wide enough — keep the hole, laser can cut it
                keep_interiors.append(interior)
            # else: too narrow, fill it (skip the double-trace)
        cleaned.append(Polygon(poly.exterior, keep_interiors))

    result_clean = unary_union(cleaned)
    return _extract_paths(result_clean)


def gap_analysis(geometry, offset_mm):
    """
    Analyze gaps between copper features for isolation feasibility.

    Returns:
        list of dicts with gap info:
            - 'pair': (i, j) polygon indices
            - 'gap_mm': gap distance in mm
            - 'status': 'ok', 'tight', 'overlap'
    """
    if isinstance(geometry, Polygon):
        return []

    polys = list(geometry.geoms)
    gaps = []
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            d = polys[i].distance(polys[j])
            if d < 5.0:  # only report gaps under 5mm
                if d >= 2 * offset_mm:
                    status = 'ok'
                elif d >= offset_mm:
                    status = 'tight'
                else:
                    status = 'overlap'
                gaps.append({
                    'pair': (i, j),
                    'gap_mm': d,
                    'status': status,
                    'min_offset': d / 2,
                })
    gaps.sort(key=lambda g: g['gap_mm'])
    return gaps


def deduplicate_paths(paths, min_dist_mm=0.05):
    """
    Remove path segments that run too close to already-drawn paths.

    Walks each path in order. If a segment falls within min_dist_mm of
    any previously drawn path, the pen lifts (segment skipped). When
    the path exits the overlap zone, the pen drops and continues.

    This prevents the laser from burning twice in the same area.

    Args:
        paths: list of LinearRing/LineString (isolation paths)
        min_dist_mm: minimum distance — segments closer than this to
                     existing paths get skipped. Set to laser beam width.

    Returns:
        list of LineString segments (may be more than input if paths were split)
    """
    from shapely.geometry import LineString as LS, MultiLineString as MLS

    if min_dist_mm <= 0 or not paths:
        return [LS(p.coords) for p in paths]

    drawn_area = None  # union of buffered already-drawn paths
    result = []

    for path in paths:
        line = LS(path.coords)

        if drawn_area is not None:
            # Subtract already-covered area from this path
            remaining = line.difference(drawn_area)
            if not remaining.is_empty:
                if isinstance(remaining, LS):
                    result.append(remaining)
                elif isinstance(remaining, MLS):
                    result.extend(remaining.geoms)
                else:
                    # GeometryCollection — extract linestrings
                    for g in remaining.geoms:
                        if isinstance(g, LS) and not g.is_empty:
                            result.append(g)
        else:
            result.append(line)

        # Mark this path's area as drawn
        path_cover = line.buffer(min_dist_mm)
        if drawn_area is None:
            drawn_area = path_cover
        else:
            drawn_area = drawn_area.union(path_cover)

    return result


def multi_pass_isolation(geometry, offset_mm, passes=1, overlap_mm=0.0,
                         mode='outline', min_gap_mm=0.0, resolution=32):
    """
    Generate multiple isolation passes with overlap.

    Args:
        geometry: copper geometry
        offset_mm: base offset for first pass
        passes: number of passes
        overlap_mm: overlap between passes (0 = no overlap)
        mode: 'outline' or 'inline'
        min_gap_mm: minimum gap for smart merging
        resolution: curve smoothness

    Returns:
        list of lists of paths (one list per pass)
    """
    all_passes = []
    for i in range(passes):
        current_offset = offset_mm + i * (offset_mm - overlap_mm)
        paths = isolation_paths(geometry, current_offset, mode,
                                min_gap_mm=min_gap_mm, resolution=resolution)
        if paths:
            all_passes.append(paths)

    return all_passes
