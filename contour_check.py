"""
contour_check.py — Check for open/unclosed contours in Gerber layers

Critical feature: detects gaps in PCB outlines and copper boundaries
that would break the laser engraving process.
"""

from shapely.geometry import LineString, MultiLineString, Polygon, MultiPolygon
from shapely.ops import linemerge, unary_union
import shapely


def check_closed_contours(geometries):
    """
    Check list of geometries for open (unclosed) contours.

    Returns:
        list of dicts with:
            - 'geometry': the problematic geometry
            - 'gap_start': (x, y) of gap start
            - 'gap_end': (x, y) of gap end
            - 'gap_size_mm': distance of gap in mm
    """
    problems = []

    for geom in geometries:
        if isinstance(geom, LineString):
            if not geom.is_ring:
                start = geom.coords[0]
                end = geom.coords[-1]
                gap = LineString([start, end]).length
                problems.append({
                    'geometry': geom,
                    'gap_start': start,
                    'gap_end': end,
                    'gap_size_mm': gap,
                })

        elif isinstance(geom, MultiLineString):
            merged = linemerge(geom)
            if isinstance(merged, LineString):
                if not merged.is_ring:
                    start = merged.coords[0]
                    end = merged.coords[-1]
                    gap = LineString([start, end]).length
                    problems.append({
                        'geometry': merged,
                        'gap_start': start,
                        'gap_end': end,
                        'gap_size_mm': gap,
                    })
            elif isinstance(merged, MultiLineString):
                for line in merged.geoms:
                    if not line.is_ring:
                        start = line.coords[0]
                        end = line.coords[-1]
                        gap = LineString([start, end]).length
                        problems.append({
                            'geometry': line,
                            'gap_start': start,
                            'gap_end': end,
                            'gap_size_mm': gap,
                        })

        elif isinstance(geom, Polygon):
            if not geom.is_valid:
                problems.append({
                    'geometry': geom,
                    'gap_start': None,
                    'gap_end': None,
                    'gap_size_mm': 0,
                })

    return problems


def auto_close_contours(geometries, tolerance_mm=0.1):
    """
    Attempt to auto-close contours with gaps smaller than tolerance.

    Returns:
        (closed_geometries, warnings)
        - closed_geometries: list with gaps closed where possible
        - warnings: list of strings for gaps too large to close
    """
    closed = []
    warnings = []

    for geom in geometries:
        if isinstance(geom, LineString) and not geom.is_ring:
            start = geom.coords[0]
            end = geom.coords[-1]
            gap = LineString([start, end]).length

            if gap <= tolerance_mm:
                # Close it by adding start point at end
                coords = list(geom.coords) + [geom.coords[0]]
                closed.append(Polygon(coords))
            else:
                warnings.append(
                    f"Gap {gap:.3f} mm at ({start[0]:.2f}, {start[1]:.2f}) "
                    f"-> ({end[0]:.2f}, {end[1]:.2f}) — too large to auto-close"
                )
                closed.append(geom)  # keep as-is
        else:
            closed.append(geom)

    return closed, warnings
