"""Tests for hatch.py: raster (hatch) fill in HPGL-ready line strings."""
import math
import os
import sys

import pytest
from shapely.geometry import LineString, Polygon, box

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hatch import ablate_region, hatch_lines  # noqa: E402


def total(lines):
    return sum(l.length for l in lines)


def test_square_horizontal():
    lines = hatch_lines(box(0, 0, 10, 10), 1.0)
    # rows at y = 0.5, 1.5 .. 9.5: ten rows of 10 mm, centred so the edges get half a pitch
    assert len(lines) == 10
    assert total(lines) == pytest.approx(100.0)
    assert all(abs(l.coords[0][1] - l.coords[-1][1]) < 1e-9 for l in lines)


def test_serpentine():
    lines = hatch_lines(box(0, 0, 10, 10), 1.0)
    dirs = [math.copysign(1, l.coords[-1][0] - l.coords[0][0]) for l in lines]
    assert dirs == [1, -1] * 5


def test_hole_is_skipped():
    ring = Polygon(box(0, 0, 10, 10).exterior.coords, [box(3, 3, 7, 7).exterior.coords])
    lines = hatch_lines(ring, 1.0)
    assert total(lines) == pytest.approx(100.0 - 16.0)
    for l in lines:
        assert not l.intersection(box(3.01, 3.01, 6.99, 6.99)).length


def test_angle_90_is_vertical():
    lines = hatch_lines(box(0, 0, 10, 4), 1.0, angle_deg=90)
    assert len(lines) == 10
    assert all(abs(l.coords[0][0] - l.coords[-1][0]) < 1e-6 for l in lines)
    assert total(lines) == pytest.approx(40.0)


def test_cross_adds_second_direction():
    one = hatch_lines(box(0, 0, 10, 10), 1.0)
    two = hatch_lines(box(0, 0, 10, 10), 1.0, cross=True)
    assert total(two) == pytest.approx(2 * total(one))


def test_bad_pitch():
    with pytest.raises(ValueError):
        hatch_lines(box(0, 0, 1, 1), 0)


def test_empty_region():
    assert hatch_lines(Polygon(), 0.1) == []


def test_ablate_region_bbox_margin():
    copper = box(2, 2, 4, 4)
    r = ablate_region(copper, 0.5, margin_mm=1.0)
    # board = copper bbox + 1 mm = 4 x 4 = 16; minus copper grown by 0.5 (3x3 with round corners)
    grown = copper.buffer(0.5)
    assert r.area == pytest.approx(16.0 - grown.area, rel=1e-6)
    assert not r.intersects(copper)


def test_ablate_region_with_board():
    copper = box(2, 2, 4, 4)
    board = box(0, 0, 10, 10)
    r = ablate_region(copper, 0.0, board=board)
    assert r.area == pytest.approx(100.0 - 4.0)


def test_lines_are_linestrings():
    lines = hatch_lines(box(0, 0, 3, 3), 1.0, angle_deg=30)
    assert lines and all(isinstance(l, LineString) for l in lines)
    for l in lines:
        assert box(0, 0, 3, 3).buffer(1e-6).contains(l)
