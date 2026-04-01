"""
hpgl_export.py — HPGL file generator for laser engraving

HPGL coordinate system: 0.025mm per unit (40 units/mm)
Commands: IN (init), SP (select pen), PU (pen up), PD (pen down), PA (plot abs)
"""

from shapely.geometry import MultiPolygon, Polygon, MultiLineString, LineString


UNITS_PER_MM = 40.0  # 0.025mm per HPGL unit


def coords_to_hpgl(coords):
    """Convert coordinate sequence to HPGL integer pairs."""
    return ','.join(
        f"{int(round(x * UNITS_PER_MM))},{int(round(y * UNITS_PER_MM))}"
        for x, y in coords
    )


def linestring_to_hpgl(line):
    """Convert a Shapely LineString to HPGL move+draw commands."""
    coords = list(line.coords)
    if len(coords) < 2:
        return ''
    # Pen up, move to start
    x0 = int(round(coords[0][0] * UNITS_PER_MM))
    y0 = int(round(coords[0][1] * UNITS_PER_MM))
    cmds = f"PU{x0},{y0};"
    # Pen down, draw to remaining points
    rest = coords_to_hpgl(coords[1:])
    cmds += f"PD{rest};"
    return cmds


def geometry_to_hpgl(geom):
    """Convert any Shapely geometry to HPGL commands."""
    cmds = []

    if isinstance(geom, (Polygon, MultiPolygon)):
        polys = [geom] if isinstance(geom, Polygon) else list(geom.geoms)
        for poly in polys:
            # Exterior ring
            cmds.append(linestring_to_hpgl(poly.exterior))
            # Interior rings (holes)
            for interior in poly.interiors:
                cmds.append(linestring_to_hpgl(interior))

    elif isinstance(geom, (LineString, MultiLineString)):
        lines = [geom] if isinstance(geom, LineString) else list(geom.geoms)
        for line in lines:
            cmds.append(linestring_to_hpgl(line))

    elif hasattr(geom, 'geoms'):
        for g in geom.geoms:
            cmds.append(geometry_to_hpgl(g))

    return '\n'.join(c for c in cmds if c)


def export_hpgl(geometries, filename, pen=1):
    """
    Export list of Shapely geometries to HPGL file.

    Args:
        geometries: list of Shapely geometry objects (in mm coordinates)
        filename: output .hpgl file path
        pen: pen number (default 1)
    """
    with open(filename, 'w') as f:
        f.write('IN;\n')
        f.write(f'SP{pen};\n')

        for geom in geometries:
            hpgl = geometry_to_hpgl(geom)
            if hpgl:
                f.write(hpgl + '\n')

        f.write('PU;\n')
        f.write('SP0;\n')

    return filename
