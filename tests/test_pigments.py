"""Pigment assignment, persistence and independent animation."""

from collections import Counter
from random import Random

import pytest

from chromatophore_simulator.model import (
    Chromatophore,
    ChromatophoreField,
    Pigment,
    ResponseParameters,
)
from chromatophore_simulator.patterns import Pattern


def test_default_field_has_equal_pigment_populations() -> None:
    """The 50 × 50 field contains 625 independent cells of each pigment."""
    field = ChromatophoreField()
    assert len(field.cells) == 2500
    assert Counter(cell.pigment for cell in field.cells) == dict.fromkeys(Pigment, 625)
    assert len({id(cell) for cell in field.cells}) == 2500


def test_odd_width_field_preserves_spatial_tile() -> None:
    """Pigment placement repeats in two dimensions rather than following flat indices."""
    field = ChromatophoreField(3, 3)
    assert tuple(cell.pigment for cell in field.cells) == (
        Pigment.YELLOW,
        Pigment.RED,
        Pigment.YELLOW,
        Pigment.BROWN,
        Pigment.BLACK,
        Pigment.BROWN,
        Pigment.YELLOW,
        Pigment.RED,
        Pigment.YELLOW,
    )


@pytest.mark.parametrize("shape", [(1, 1), (1, 5), (5, 1), (3, 7)])
def test_small_and_rectangular_fields(shape: tuple[int, int]) -> None:
    """Small fields retain valid, deterministic pigment assignments.

    :param shape: Row and column counts, including single-axis fields.
    """
    first = ChromatophoreField(*shape)
    second = ChromatophoreField(*shape)
    assert len(first.cells) == shape[0] * shape[1]
    assert all(isinstance(cell.pigment, Pigment) for cell in first.cells)
    assert [cell.pigment for cell in first.cells] == [cell.pigment for cell in second.cells]


def test_pigments_survive_all_target_commands() -> None:
    """Patterns and global commands alter expansion without replacing or recolouring cells."""
    field = ChromatophoreField(12, 12)
    cells = field.cells
    pigments = tuple(cell.pigment for cell in cells)
    for pattern in Pattern:
        field.apply_pattern(pattern, Random(42))
        field.update(10.0)
        assert field.cells is cells
        assert tuple(cell.pigment for cell in cells) == pigments
        assert all(cell.expansion == cell.target_expansion for cell in cells)
    field.randomise(Random(42))
    field.set_expansion(1.0)
    field.update(10.0)
    field.set_expansion(0.0)
    field.update(10.0)
    assert tuple(cell.pigment for cell in cells) == pigments
    assert all(cell.expansion == 0.0 for cell in cells)


def test_different_pigments_animate_independently() -> None:
    """Each pigment's cell retains its own target, size and response countdown."""
    field = ChromatophoreField(2, 2, ResponseParameters(1.0, 0.5))
    yellow, red, brown, black = field.cells
    yellow.set_target(1.0)
    red.set_target(0.5, response_delay=0.25)
    brown.set_target(0.25)
    field.update(0.5)
    assert [cell.expansion for cell in field.cells] == pytest.approx([0.5, 0.25, 0.25, 0.0])
    yellow.set_target(0.0)
    black.set_target(1.0)
    field.update(0.5)
    assert [cell.expansion for cell in field.cells] == pytest.approx([0.25, 0.5, 0.25, 0.5])


def test_individual_cell_defaults_to_brown() -> None:
    """Existing positional expansion arguments still work for single cells."""
    cell = Chromatophore(0.2, 0.8)
    assert cell.pigment is Pigment.BROWN
    assert cell.expansion == 0.2
    assert cell.target_expansion == 0.8


@pytest.mark.parametrize("pigment", ["yellow", None, 1])
def test_invalid_pigment_is_rejected(pigment: object) -> None:
    """Reject invalid identities before they reach palette lookup in the renderer.

    :param pigment: Invalid pigment value.
    """
    with pytest.raises(ValueError, match="Pigment"):
        Chromatophore(pigment=pigment)
