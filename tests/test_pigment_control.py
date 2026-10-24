"""Independent pigment targets across static patterns, delay and dynamic signals."""

from dataclasses import astuple
from random import Random

import pytest

from chromatophore_simulator.dynamics import DynamicDisplay
from chromatophore_simulator.model import ChromatophoreField, Pigment, ResponseParameters
from chromatophore_simulator.patterns import Pattern


def test_levels_scale_original_targets_without_compounding() -> None:
    """Changing one level preserves other groups, current sizes and source geometry."""
    field = ChromatophoreField(3, 5)
    targets = tuple(index / 15 for index in range(15))
    field.set_targets(targets)
    field.update(0.4)
    sizes = tuple(cell.expansion for cell in field.cells)
    for level in (0.25, 0.5, 0.0, 1.0):
        field.set_pigment_level(Pigment.YELLOW, level)
        assert tuple(cell.expansion for cell in field.cells) == sizes
        assert tuple(cell.target_expansion for cell in field.cells) == pytest.approx(
            tuple(
                target * (level if cell.pigment is Pigment.YELLOW else 1)
                for cell, target in zip(field.cells, targets, strict=True)
            )
        )


@pytest.mark.parametrize("level", [-0.1, 1.1, float("nan"), float("inf")])
def test_invalid_levels_are_atomic(level: float) -> None:
    """Invalid levels must not alter a running display or any cell.

    :param level: Invalid normalised target multiplier.
    """
    field = ChromatophoreField(2, 2)
    field.start_dynamic(DynamicDisplay.FLASH)
    before = tuple(astuple(cell) for cell in field.cells)
    controller = field.dynamic
    with pytest.raises(ValueError):
        field.set_pigment_level(Pigment.RED, level)
    assert field.pigment_levels[Pigment.RED] == 1
    assert field.dynamic is controller
    assert tuple(astuple(cell) for cell in field.cells) == before


def test_levels_are_read_only_and_unknown_pigment_is_rejected() -> None:
    """Callers cannot bypass validation by editing the exposed level mapping."""
    field = ChromatophoreField(2, 2)
    with pytest.raises(TypeError):
        field.pigment_levels[Pigment.YELLOW] = 0.5
    with pytest.raises(ValueError):
        field.set_pigment_level("Unknown", 0.5)


def test_static_level_changes_preserve_other_groups_delay() -> None:
    """Group edits honour delay and repeating a value never restarts a countdown."""
    field = ChromatophoreField(2, 2, ResponseParameters(1, 1, 0.5))
    field.set_expansion(1)
    field.update(0.2)
    other_delay = field.cells[1]._delay_remaining
    field.set_pigment_level(Pigment.YELLOW, 0.5)
    assert field.cells[1]._delay_remaining == other_delay
    field.update(0.25)
    field.set_pigment_level(Pigment.YELLOW, 0.5)
    field.update(0.3)
    assert field.cells[0].expansion == pytest.approx(0.05)
    assert field.cells[1].expansion == pytest.approx(0.25)


def test_levels_persist_across_commands_and_reset_restores_pattern() -> None:
    """Static commands use the mix and reset recovers the current source targets."""
    field = ChromatophoreField(5, 7)
    field.set_pigment_level(Pigment.RED, 0)
    field.randomise(Random(1))
    assert all(cell.target_expansion == 0 for cell in field.cells if cell.pigment is Pigment.RED)
    field.apply_pattern(Pattern.UNIFORM, Random(1))
    assert all(cell.target_expansion == 0 for cell in field.cells if cell.pigment is Pigment.RED)
    field.reset_pigment_levels()
    assert all(cell.target_expansion == 0.5 for cell in field.cells)


def test_dynamic_levels_preserve_phase_delay_and_hold_sizes() -> None:
    """Scaling affects delayed signals without restarting phase; Hold freezes actual sizes."""
    reference = ChromatophoreField(2, 2, ResponseParameters(1, 1, 0.5))
    mixed = ChromatophoreField(2, 2, reference.response)
    for field in (reference, mixed):
        field.start_dynamic(DynamicDisplay.FLASH)
        field.update(0.25)
    phase = mixed.dynamic.phase_seconds
    mixed.set_pigment_level(Pigment.YELLOW, 0.25)
    assert mixed.dynamic.phase_seconds == phase
    assert all(cell.target_expansion == 0 for cell in mixed.cells)
    for field in (reference, mixed):
        field.update(0.5)
    assert mixed.dynamic.phase_seconds == reference.dynamic.phase_seconds
    for original, cell in zip(reference.cells, mixed.cells, strict=True):
        scale = 0.25 if cell.pigment is Pigment.YELLOW else 1
        assert cell.target_expansion == pytest.approx(original.target_expansion * scale)
    sizes = tuple(cell.expansion for cell in mixed.cells)
    mixed.hold()
    mixed.update(2)
    assert tuple(cell.expansion for cell in mixed.cells) == sizes
    mixed.set_pigment_level(Pigment.YELLOW, 0.5)
    assert mixed.cells[0].target_expansion == pytest.approx(sizes[0] * 0.5)
    assert mixed.cells[1].target_expansion == sizes[1]
