"""Time-varying signals and their integration with independently animated cells."""

from random import Random

import pytest

from chromatophore_simulator.dynamics import DynamicController, DynamicDisplay
from chromatophore_simulator.model import ChromatophoreField, ResponseParameters
from chromatophore_simulator.patterns import Pattern


@pytest.mark.parametrize("display", list(DynamicDisplay))
@pytest.mark.parametrize("shape", [(1, 1), (1, 9), (9, 1), (7, 13)])
def test_dynamic_targets_are_bounded(display: DynamicDisplay, shape: tuple[int, int]) -> None:
    """All displays support small and rectangular fields.

    :param display: Signal under test.
    :param shape: Row and column counts.
    """
    controller = DynamicController(display, *shape)
    snapshots = [controller.targets_at(time) for time in (0, 2, 4, 8, 12, 20)]
    assert all(len(targets) == shape[0] * shape[1] for targets in snapshots)
    assert all(0 <= value <= 1 for targets in snapshots for value in targets)
    assert len(set(snapshots)) > 1


def test_travelling_wave_moves_left_to_right() -> None:
    """The peak shifts to larger columns as time advances."""
    controller = DynamicController(DynamicDisplay.TRAVELLING_WAVE, 1, 51)
    first = controller.targets_at(4)
    second = controller.targets_at(8)
    assert first.index(max(first)) < second.index(max(second))


def test_radial_pulse_moves_out_from_centre() -> None:
    """The centre activates first; a ring farther out activates later."""
    controller = DynamicController(DynamicDisplay.RADIAL_PULSE, 11, 11)
    assert controller.targets_at(0)[60] == 1.0
    assert controller.targets_at(8)[60] == 0.0
    assert controller.targets_at(8)[65] == 1.0


def test_flash_is_uniform_and_repeats() -> None:
    """Flash alternates globally between two seconds on and two seconds off."""
    controller = DynamicController(DynamicDisplay.FLASH, 3, 5)
    assert set(controller.targets_at(0)) == {1.0}
    assert set(controller.targets_at(2)) == {0.0}
    assert controller.targets_at(4) == controller.targets_at(0)


def test_local_excitation_reaches_neighbours_before_distant_cells() -> None:
    """Four-connected propagation activates the centre, then adjacent regions."""
    controller = DynamicController(DynamicDisplay.LOCAL_EXCITATION, 5, 5)
    assert sum(controller.targets_at(0)) == 1.0
    assert controller.targets_at(0)[12] == 1.0
    early = controller.targets_at(0.13)
    assert sum(early) == 5.0
    assert early[0] == 0.0
    assert controller.targets_at(0.5)[0] == 1.0
    assert sum(controller.targets_at(5)) == 0.0


def test_signal_delay_and_speed_history() -> None:
    """A delayed signal uses the historical phase even after changing speed."""
    controller = DynamicController(DynamicDisplay.MOVING_BANDS, 3, 5)
    assert controller.advance(0.25, 0.5) is None
    assert controller.advance(0.25, 0.5) == controller.targets_at(0)
    controller.speed = 2.0
    assert controller.advance(0.25, 0.5) == controller.targets_at(0.25)
    assert controller.advance(0.5, 0.5) == controller.targets_at(1.0)


def test_dynamic_delay_does_not_starve_movement() -> None:
    """Continuous target changes do not repeatedly restart the response countdown."""
    field = ChromatophoreField(5, 5, ResponseParameters(1, 1, 0.5))
    field.start_dynamic(DynamicDisplay.MOVING_BANDS)
    field.update(0.25)
    assert all(cell.expansion == 0 for cell in field.cells)
    field.update(1)
    assert any(cell.expansion > 0.4 for cell in field.cells)


def test_dynamic_integration_is_frame_rate_independent() -> None:
    """Fixed substeps give equal state for different frame-time partitions."""
    first = ChromatophoreField(3, 7)
    second = ChromatophoreField(3, 7)
    for field in (first, second):
        field.start_dynamic(DynamicDisplay.MOVING_BANDS)
    first.update(1.0)
    for _ in range(100):
        second.update(0.01)
    assert [cell.expansion for cell in first.cells] == pytest.approx(
        [cell.expansion for cell in second.cells]
    )


def test_hold_static_commands_and_identity() -> None:
    """Holding and static selection stop the signal without replacing cells or pigments."""
    field = ChromatophoreField(5, 5)
    cells = field.cells
    pigments = [cell.pigment for cell in cells]
    field.start_dynamic(DynamicDisplay.MOVING_BANDS)
    field.update(1)
    before = [cell.expansion for cell in cells]
    field.hold()
    field.update(2)
    assert [cell.expansion for cell in cells] == before
    assert field.dynamic is None
    for operation in ("pattern", "expand", "randomise", "targets"):
        field.start_dynamic(DynamicDisplay.FLASH)
        if operation == "pattern":
            field.apply_pattern(Pattern.SPOTS, Random(0))
        elif operation == "expand":
            field.set_expansion(1)
        elif operation == "randomise":
            field.randomise(Random(0))
        else:
            field.set_targets((0.5,) * 25)
        assert field.dynamic is None
    assert field.cells is cells
    assert [cell.pigment for cell in cells] == pigments


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf")])
def test_invalid_dynamic_time(value: float) -> None:
    """Invalid timing never reaches signal maths.

    :param value: Invalid time or delay.
    """
    controller = DynamicController(DynamicDisplay.FLASH, 1, 1)
    with pytest.raises(ValueError):
        controller.advance(value, 0)
    with pytest.raises(ValueError):
        controller.advance(0, value)
    with pytest.raises(ValueError):
        controller.targets_at(value)


def test_changing_mottle_holds_targets_and_reproduces_past_patterns() -> None:
    """Mottle changes on schedule, is seeded, and survives backward time sampling."""
    controller = DynamicController(DynamicDisplay.CHANGING_MOTTLE, 12, 12, Random(42))
    first = controller.targets_at(0)
    assert controller.targets_at(5.99) is first
    second = controller.targets_at(6)
    assert second != first
    assert controller.targets_at(12) != second
    assert controller.targets_at(0) == first
    same = DynamicController(DynamicDisplay.CHANGING_MOTTLE, 12, 12, Random(42))
    other = DynamicController(DynamicDisplay.CHANGING_MOTTLE, 12, 12, Random(43))
    assert same.targets_at(6) == second
    assert other.targets_at(0) != first


def test_changing_mottle_respects_speed_delay_and_cell_continuity() -> None:
    """New targets arrive through the delayed clock without snapping cells to them."""
    controller = DynamicController(DynamicDisplay.CHANGING_MOTTLE, 5, 5, Random(42))
    first = controller.targets_at(0)
    controller.speed = 2
    assert controller.advance(3, 0.5) == first
    assert controller.advance(0.5, 0.5) == controller.targets_at(6)
    field = ChromatophoreField(5, 5, ResponseParameters(0.25, 0.25))
    cells = field.cells
    field.start_dynamic(DynamicDisplay.CHANGING_MOTTLE, Random(42))
    field.update(5.9)
    before = [cell.expansion for cell in cells]
    old_targets = [cell.target_expansion for cell in cells]
    field.update(0.2)
    assert [cell.target_expansion for cell in cells] != old_targets
    assert all(abs(cell.expansion - old) <= 0.05 + 1e-9 for cell, old in zip(cells, before))
    assert field.cells is cells
