"""Pattern geometry and transitions, checked without a graphics dependency."""

from random import Random

import pytest

from chromatophore_simulator.model import ChromatophoreField, ResponseParameters
from chromatophore_simulator.patterns import Pattern, generate_targets


@pytest.mark.parametrize("pattern", list(Pattern))
@pytest.mark.parametrize("shape", [(50, 50), (3, 17), (1, 1), (1, 13), (13, 1)])
def test_target_dimensions_and_range(pattern: Pattern, shape: tuple[int, int]) -> None:
    """Every pattern supports rectangular and degenerate grids with valid targets.

    :param pattern: Pattern under test.
    :param shape: Field rows and columns.
    """
    targets = generate_targets(pattern, *shape, Random(42))
    assert len(targets) == shape[0] * shape[1]
    assert all(0.0 <= value <= 1.0 for value in targets)


def test_uniform_and_checkerboard() -> None:
    """Uniform sets half expansion; checks alternate at six-cell boundaries."""
    assert set(generate_targets(Pattern.UNIFORM, 12, 12, Random(0))) == {0.5}
    checks = generate_targets(Pattern.CHECKERBOARD, 12, 12, Random(0))
    assert checks[0] == checks[5] == checks[5 * 12 + 5] == 1.0
    assert checks[6] == checks[6 * 12] == 0.0
    assert checks[6 * 12 + 6] == 1.0


def test_band_orientation() -> None:
    """Horizontal bands are constant along rows; vertical bands along columns."""
    horizontal = generate_targets(Pattern.HORIZONTAL_BANDS, 12, 12, Random(0))
    vertical = generate_targets(Pattern.VERTICAL_BANDS, 12, 12, Random(0))
    assert horizontal[:12] == (1.0,) * 12
    assert horizontal[6 * 12 : 7 * 12] == (0.0,) * 12
    assert vertical[:12] == (1.0,) * 6 + (0.0,) * 6
    for row in range(12):
        for column in range(12):
            assert horizontal[row * 12 + column] == vertical[column * 12 + row]


def test_spots_are_circular_and_repeat() -> None:
    """Spot centres expand and corners contract, repeating every twelve cells."""
    targets = generate_targets(Pattern.SPOTS, 24, 24, Random(0))
    assert targets[5 * 24 + 5] == targets[17 * 24 + 17] == 1.0
    assert targets[0] == targets[12 * 24 + 12] == 0.0
    # Equal distances along either axis must give the same circular footprint.
    for row in range(12):
        for column in range(12):
            assert targets[row * 24 + column] == targets[column * 24 + row]


def test_radial_gradient_is_symmetric_and_fades_outward() -> None:
    """The geometric centre is strongest, with a monotonic fade towards corners."""
    targets = generate_targets(Pattern.RADIAL_GRADIENT, 9, 9, Random(0))
    assert targets[4 * 9 + 4] == 1.0
    assert targets[0] == targets[-1] == 0.0
    assert targets[4 * 9 + 4] > targets[4 * 9 + 5] > targets[4 * 9 + 6]
    assert targets == pytest.approx(tuple(reversed(targets)))
    assert generate_targets(Pattern.RADIAL_GRADIENT, 1, 1, Random(0)) == (1.0,)


def test_mottle_is_seeded_and_spatially_correlated() -> None:
    """Mottle is reproducible with a seed and varies smoothly between neighbours."""
    first = generate_targets(Pattern.RANDOM_MOTTLE, 50, 50, Random(42))
    assert first == generate_targets(Pattern.RANDOM_MOTTLE, 50, 50, Random(42))
    assert first != generate_targets(Pattern.RANDOM_MOTTLE, 50, 50, Random(43))
    assert max(first) - min(first) > 0.5
    for row in range(49):
        for column in range(49):
            index = row * 50 + column
            assert abs(first[index] - first[index + 1]) <= 1 / 6
            assert abs(first[index] - first[index + 50]) <= 1 / 6


@pytest.mark.parametrize(
    "pattern", [value for value in Pattern if value is not Pattern.RANDOM_MOTTLE]
)
def test_fixed_patterns_do_not_consume_randomness(pattern: Pattern) -> None:
    """Selecting a fixed pattern leaves the mottle generator's sequence alone.

    :param pattern: Non-random pattern under test.
    """
    source = Random(42)
    state = source.getstate()
    generate_targets(pattern, 12, 12, source)
    assert source.getstate() == state


def test_pattern_switch_animates_existing_cells_with_delay() -> None:
    """Selecting a new pattern changes targets only, respecting latency and rates."""
    field = ChromatophoreField(12, 12, ResponseParameters(0.5, 1.0, 0.25))
    cells = field.cells
    field.apply_pattern(Pattern.UNIFORM, Random(0))
    field.update(2.0)
    field.apply_pattern(Pattern.CHECKERBOARD, Random(0))
    assert field.cells is cells
    assert all(cell.expansion == 0.5 for cell in cells)
    field.update(0.25)
    assert all(cell.expansion == 0.5 for cell in cells)
    field.update(0.2)
    assert cells[0].expansion == pytest.approx(0.6)
    assert cells[6].expansion == pytest.approx(0.3)
    # Switch again mid-transition without replacing the cells or snapping their sizes.
    before = tuple(cell.expansion for cell in cells)
    field.apply_pattern(Pattern.RADIAL_GRADIENT, Random(0))
    assert tuple(cell.expansion for cell in cells) == before
    field.update(10.0)
    assert all(cell.expansion == cell.target_expansion for cell in cells)


@pytest.mark.parametrize("targets", [(0.1,), (0.1, 1.1), (0.1, float("nan"))])
def test_invalid_targets_leave_field_intact(targets: tuple[float, ...]) -> None:
    """Validate an entire target array before changing any cell or its countdown.

    :param targets: Invalid target count or values.
    """
    field = ChromatophoreField(1, 2)
    field.set_expansion(0.5)
    with pytest.raises(ValueError):
        field.set_targets(targets)
    assert [cell.target_expansion for cell in field.cells] == [0.5, 0.5]
    assert field.target_description == "Uniform 50%"


@pytest.mark.parametrize("size", [0, -1, 1.5, True])
def test_invalid_pattern_dimensions(size: int | float) -> None:
    """Reject invalid grid dimensions at the public generation boundary.

    :param size: Invalid number of rows or columns.
    """
    with pytest.raises(ValueError):
        generate_targets(Pattern.UNIFORM, size, 1, Random(0))
    with pytest.raises(ValueError):
        generate_targets(Pattern.UNIFORM, 1, size, Random(0))


def test_invalid_pattern_is_rejected() -> None:
    """Reject unsupported pattern values explicitly."""
    with pytest.raises(ValueError, match="Pattern"):
        generate_targets("unknown", 1, 1, Random(0))
