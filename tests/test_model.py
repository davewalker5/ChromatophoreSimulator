"""Deterministic checks of field independence, timing and input validation."""

from random import Random

import pytest

from chromatophore_simulator.model import Chromatophore, ChromatophoreField, ResponseParameters


def test_default_field_has_independent_cells() -> None:
    """The default field contains 2,500 distinct, independently controlled cells."""
    field = ChromatophoreField(response=ResponseParameters(1.0, 1.0))
    assert len(field.cells) == 2500
    assert len({id(cell) for cell in field.cells}) == 2500
    field.cells[0].set_target(1.0)
    field.update(0.25)
    assert field.cells[0].expansion == pytest.approx(0.25)
    assert all(cell.expansion == 0.0 for cell in field.cells[1:])


def test_transitions_reverse_and_never_overshoot() -> None:
    """Commands preserve current expansion and can reverse an ongoing transition."""
    field = ChromatophoreField(1, 1, ResponseParameters(1.0, 1.0))
    field.set_expansion(1.0)
    assert field.cells[0].expansion == 0.0
    field.update(0.4)
    assert field.cells[0].expansion == pytest.approx(0.4)
    field.set_expansion(0.0)
    field.update(0.1)
    assert field.cells[0].expansion == pytest.approx(0.3)
    field.update(10.0)
    assert field.cells[0].expansion == 0.0
    field.set_expansion(1.0)
    field.update(10.0)
    assert field.cells[0].expansion == 1.0


def test_timing_is_frame_rate_independent() -> None:
    """Equal elapsed time gives equal state regardless of update frequency."""
    slow = ChromatophoreField(1, 1, ResponseParameters(1.0, 1.0))
    fast = ChromatophoreField(1, 1, ResponseParameters(1.0, 1.0))
    for field in (slow, fast):
        field.set_expansion(1.0)
    slow.update(0.5)
    for _ in range(50):
        fast.update(0.01)
    assert fast.cells[0].expansion == pytest.approx(slow.cells[0].expansion)
    fast.update(0.0)
    assert fast.cells[0].expansion == pytest.approx(0.5)


def test_random_targets_are_reproducible_and_independent() -> None:
    """Seeded randomisation changes targets only and assigns varied valid values."""
    first = ChromatophoreField(3, 4)
    second = ChromatophoreField(3, 4)
    for field in (first, second):
        field.randomise(Random(42))
    targets = [cell.target_expansion for cell in first.cells]
    assert targets == [cell.target_expansion for cell in second.cells]
    assert len(set(targets)) == 12
    assert all(0 <= target <= 1 for target in targets)
    assert all(cell.expansion == 0 for cell in first.cells)


@pytest.mark.parametrize("value", [-0.1, 1.1, float("nan"), float("inf")])
def test_invalid_expansion_does_not_mutate_field(value: float) -> None:
    """Reject invalid initial states and commands before any field mutation.

    :param value: Invalid normalised expansion.
    """
    with pytest.raises(ValueError):
        Chromatophore(expansion=value)
    with pytest.raises(ValueError):
        Chromatophore(target_expansion=value)
    field = ChromatophoreField(1, 2, ResponseParameters(1.0, 1.0))
    field.set_expansion(0.5)
    with pytest.raises(ValueError):
        field.set_expansion(value)
    assert all(cell.target_expansion == 0.5 for cell in field.cells)


@pytest.mark.parametrize("elapsed", [-1.0, float("nan"), float("inf")])
def test_invalid_elapsed_time(elapsed: float) -> None:
    """Reject elapsed times that would corrupt numerical state.

    :param elapsed: Invalid elapsed seconds.
    """
    with pytest.raises(ValueError):
        ChromatophoreField(1, 1, ResponseParameters(1.0, 1.0)).update(elapsed)


@pytest.mark.parametrize("size", [0, -1, 1.5, True])
def test_invalid_dimensions(size: int | float) -> None:
    """Both field dimensions must be positive integers.

    :param size: Invalid row or column count.
    """
    with pytest.raises(ValueError):
        ChromatophoreField(rows=size)
    with pytest.raises(ValueError):
        ChromatophoreField(columns=size)


def test_separate_rates_and_partial_target() -> None:
    """Expansion and contraction use their own rates and stop at partial targets."""
    field = ChromatophoreField(response=ResponseParameters(0.5, 2.0), rows=1, columns=1)
    field.set_expansion(0.6)
    field.update(0.5)
    assert field.cells[0].expansion == pytest.approx(0.25)
    field.update(1.0)
    assert field.cells[0].expansion == 0.6
    field.set_expansion(0.1)
    field.update(0.2)
    assert field.cells[0].expansion == pytest.approx(0.2)
    field.update(0.2)
    assert field.cells[0].expansion == 0.1


@pytest.mark.parametrize("steps", [(0.5,), (0.1,) * 5, (0.25, 0.25)])
def test_delay_uses_only_remaining_frame_time(steps: tuple[float, ...]) -> None:
    """A frame crossing the delay boundary spends only its remainder on movement.

    :param steps: Different partitions of half a second of elapsed time.
    """
    field = ChromatophoreField(1, 1, ResponseParameters(0.5, 2.0, 0.25))
    field.set_expansion(1.0)
    for seconds in steps:
        field.update(seconds)
    assert field.cells[0].expansion == pytest.approx(0.125)


def test_delay_boundary_and_repeated_command() -> None:
    """Repeating a pending target does not postpone its response indefinitely."""
    field = ChromatophoreField(1, 1, ResponseParameters(1.0, 1.0, response_delay=0.5))
    field.set_expansion(1.0)
    field.update(0.25)
    assert field.cells[0].expansion == 0.0
    field.set_expansion(1.0)
    field.update(0.25)
    assert field.cells[0].expansion == 0.0
    field.update(0.1)
    assert field.cells[0].expansion == pytest.approx(0.1)


def test_retargeting_holds_current_size_and_restarts_delay() -> None:
    """New targets replace old ones during both latency and active movement."""
    field = ChromatophoreField(1, 1, ResponseParameters(1.0, 1.0, response_delay=0.5))
    field.set_expansion(1.0)
    field.update(0.25)
    field.set_expansion(0.8)
    field.update(0.5)
    assert field.cells[0].expansion == 0.0
    field.update(0.25)
    field.set_expansion(0.0)
    field.update(0.5)
    assert field.cells[0].expansion == pytest.approx(0.25)
    field.update(0.125)
    assert field.cells[0].expansion == pytest.approx(0.125)
    field.update(10.0)
    assert field.cells[0].expansion == 0.0


def test_cells_keep_independent_delays() -> None:
    """A later command to one cell does not reset another cell's countdown."""
    field = ChromatophoreField(1, 2, ResponseParameters(1.0, 1.0))
    first, second = field.cells
    first.set_target(1.0, 0.5)
    field.update(0.25)
    second.set_target(1.0, 0.5)
    field.update(0.5)
    assert first.expansion == pytest.approx(0.25)
    assert second.expansion == 0.0


def test_live_settings_preserve_pending_delay_and_current_size() -> None:
    """New rates apply immediately; new delay values only affect new targets."""
    field = ChromatophoreField(1, 1, ResponseParameters(1.0, 1.0, response_delay=0.5))
    field.set_expansion(1.0)
    field.update(0.25)
    field.response = ResponseParameters(2.0, 0.5, 2.0)
    field.update(0.5)
    assert field.cells[0].expansion == pytest.approx(0.5)
    field.response = ResponseParameters(0.5, 0.25, 0.0)
    field.update(0.25)
    assert field.cells[0].expansion == pytest.approx(0.625)
    field.set_expansion(0.0)
    field.update(0.5)
    assert field.cells[0].expansion == pytest.approx(0.5)


def test_randomise_obeys_delay() -> None:
    """Random targets wait for the configured delay before beginning to move."""
    field = ChromatophoreField(2, 2, ResponseParameters(1.0, 1.0, response_delay=0.5))
    field.randomise(Random(42))
    field.update(0.5)
    assert all(cell.expansion == 0.0 for cell in field.cells)
    field.update(10.0)
    assert all(cell.expansion == cell.target_expansion for cell in field.cells)


@pytest.mark.parametrize("name", ["expansion_rate", "contraction_rate", "response_delay"])
@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf"), -float("inf")])
def test_invalid_response_settings(name: str, value: float) -> None:
    """Reject invalid settings before they can enter the simulation.

    :param name: Parameter under test.
    :param value: Invalid parameter value.
    """
    with pytest.raises(ValueError):
        ResponseParameters(**{name: value})


@pytest.mark.parametrize("name", ["expansion_rate", "contraction_rate"])
def test_zero_rate_is_rejected(name: str) -> None:
    """Rates must be positive so a target can always be reached.

    :param name: Rate parameter under test.
    """
    with pytest.raises(ValueError):
        ResponseParameters(**{name: 0.0})


def test_invalid_cell_time_or_delay_preserves_state() -> None:
    """Direct cell calls validate timing inputs before modifying state."""
    cell = Chromatophore(0.2, 0.4)
    with pytest.raises(ValueError):
        cell.set_target(0.8, -1.0)
    with pytest.raises(ValueError):
        cell.update(float("nan"), ResponseParameters())
    assert cell.expansion == 0.2
    assert cell.target_expansion == 0.4
