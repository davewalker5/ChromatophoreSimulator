"""Geometry bounds, reproducibility and exact coverage of irregular organs."""

from collections import Counter
from dataclasses import FrozenInstanceError
from math import hypot, pi, sqrt
from random import Random

import pytest

from chromatophore_simulator.coverage import circle_rectangle_area
from chromatophore_simulator.model import ChromatophoreField
from chromatophore_simulator.morphology import MAXIMUM_RADIUS_RATIO, generate_layout
from chromatophore_simulator.skin_renderer import sample_pigment_areas


@pytest.mark.parametrize("shape", [(1, 1), (1, 7), (7, 1), (3, 5), (50, 50)])
def test_layout_is_reproducible_bounded_and_non_overlapping(shape: tuple[int, int]) -> None:
    """Every expanded disc fits its patch and remains clear of every nearby disc.

    :param shape: Logical dimensions, including narrow and odd-sized fields.
    """
    rows, columns = shape
    layout = generate_layout(rows, columns)
    assert layout == generate_layout(rows, columns)
    assert layout != generate_layout(rows, columns, 0)
    assert len(layout) == rows * columns
    counts = Counter(organ.pigment_index for organ in layout)
    assert max(counts.values()) - min(counts.values()) <= 1
    for index, organ in enumerate(layout):
        assert 0 < organ.radius_ratio <= MAXIMUM_RADIUS_RATIO
        assert organ.radius_ratio <= min(organ.x, columns - organ.x, organ.y, rows - organ.y)
        row, column = divmod(index, columns)
        for nr in range(max(0, row - 2), min(rows, row + 3)):
            for nc in range(max(0, column - 2), min(columns, column + 3)):
                neighbour = nr * columns + nc
                if neighbour == index:
                    continue
                other = layout[neighbour]
                assert organ.radius_ratio + other.radius_ratio < hypot(
                    organ.x - other.x, organ.y - other.y
                )
    with pytest.raises(FrozenInstanceError):
        layout[0].x = 0


def test_layout_varies_without_consuming_pattern_randomness() -> None:
    """Positions and sizes differ but stay fixed through commands and updates."""
    field = ChromatophoreField()
    geometry = field.geometry
    assert len({round(organ.radius_ratio, 3) for organ in geometry}) > 50
    assert len({round(organ.x % 1, 3) for organ in geometry}) > 50
    source = Random(42)
    reference = Random(42)
    field.randomise(source)
    assert tuple(cell.target_expansion for cell in field.cells) == tuple(
        reference.random() for _ in field.cells
    )
    field.update(1)
    field.set_expansion(1)
    field.hold()
    assert field.geometry is geometry


@pytest.mark.parametrize(
    "arguments", [(0, 2, 1), (2, -1, 1), (2.5, 2, 1), (2, 2, -1), (2, 2, 2**32), (2, 2, True)]
)
def test_invalid_layout_arguments_are_rejected(arguments: tuple[int, int, int]) -> None:
    """Reject invalid dimensions and seeds before any field can use the layout.

    :param arguments: Invalid row, column and seed combination.
    """
    with pytest.raises(ValueError):
        generate_layout(*arguments)


def test_circle_area_boundaries_and_partition_conservation() -> None:
    """A disc crossing four sample corners loses no area and is counted only once."""
    radius = 0.4
    assert circle_rectangle_area(0, 0, radius, (-1, -1, 1, 1)) == pytest.approx(pi * radius**2)
    assert circle_rectangle_area(0, 0, radius, (0, 0, 1, 1)) == pytest.approx(pi * radius**2 / 4)
    assert circle_rectangle_area(0, 0, radius, (radius, 0, 1, 1)) == 0
    assert circle_rectangle_area(0, 0, 0, (-1, -1, 1, 1)) == 0
    assert circle_rectangle_area(0, 0, radius, (-0.1, -0.1, 0.1, 0.1)) == pytest.approx(0.04)
    pieces = [
        circle_rectangle_area(0.13, -0.07, radius, bounds)
        for bounds in ((-1, -1, 0, 0), (0, -1, 1, 0), (-1, 0, 0, 1), (0, 0, 1, 1))
    ]
    assert sum(pieces) == pytest.approx(pi * radius**2)


def test_partial_circle_area_matches_independent_numerical_integration() -> None:
    """An asymmetric arc intersection agrees with midpoint quadrature."""
    left, top, right, bottom = -0.3, -0.12, 0.27, 0.36
    radius = 0.4
    steps = 20000
    step = (right - left) / steps
    numerical = 0.0
    for index in range(steps):
        x = left + (index + 0.5) * step
        height = sqrt(radius**2 - x**2)
        numerical += max(0, min(bottom, height) - max(top, -height)) * step
    assert circle_rectangle_area(0, 0, radius, (left, top, right, bottom)) == pytest.approx(
        numerical, abs=1e-8
    )


@pytest.mark.parametrize("span", [1, 2, 4])
def test_sample_partition_preserves_all_pigment_area(span: int) -> None:
    """Irregular boundary-crossing discs conserve area, including partial sample edges.

    :param span: Number of logical slots along a sample side.
    """
    field = ChromatophoreField(5, 7)
    field.set_expansion(1)
    field.update(4)
    area = 0.0
    for top in range(0, field.rows, span):
        for left in range(0, field.columns, span):
            bounds = (left, top, min(left + span, field.columns), min(top + span, field.rows))
            area += sum(sample_pigment_areas(field, 11, bounds).values())
    assert area == pytest.approx(sum(pi * organ.radius_ratio**2 for organ in field.geometry))


@pytest.mark.parametrize(
    "radius,bounds",
    [
        (-1, (0, 0, 1, 1)),
        (float("nan"), (0, 0, 1, 1)),
        (1, (1, 0, 0, 1)),
        (1, (0, 0, float("inf"), 1)),
    ],
)
def test_invalid_coverage_is_rejected(radius: float, bounds: tuple[float, ...]) -> None:
    """Invalid geometry must not silently produce plausible coverage.

    :param radius: Possibly invalid radius.
    :param bounds: Possibly invalid rectangle.
    """
    with pytest.raises(ValueError):
        circle_rectangle_area(0, 0, radius, bounds)
