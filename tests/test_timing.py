"""Natural kinetics, stable coordination profiles and compatibility with signal timing."""

from collections import defaultdict
from dataclasses import astuple
from random import Random

import pytest

from chromatophore_simulator.dynamics import DynamicDisplay
from chromatophore_simulator.model import Chromatophore, ChromatophoreField, ResponseParameters
from chromatophore_simulator.morphology import generate_layout
from chromatophore_simulator.timing import generate_response_profiles


def test_natural_response_reference_delay_and_settling() -> None:
    """A nominal rate of four gives a 99% response in 250 ms after the explicit delay."""
    cell = Chromatophore()
    cell.set_target(1, 0.1)
    cell.update(0.1, ResponseParameters(4, 4), natural_timing=True)
    assert cell.expansion == 0
    cell.update(0.25, ResponseParameters(4, 4), natural_timing=True)
    assert cell.expansion == pytest.approx(0.99)
    cell.update(0.5, ResponseParameters(4, 4), natural_timing=True)
    assert cell.expansion == 1
    cell.set_target(0)
    cell.update(0.25, ResponseParameters(4, 4), natural_timing=True)
    assert cell.expansion == pytest.approx(0.01)
    cell.update(1, ResponseParameters(4, 4), natural_timing=True)
    assert cell.expansion == 0


def test_natural_motion_is_partition_independent_and_reverses_without_overshoot() -> None:
    """Exact exponential integration preserves time partitioning and stable reversals."""
    whole, split = Chromatophore(), Chromatophore()
    for cell in (whole, split):
        cell.set_target(1, 0.04)
    whole.update(0.2, ResponseParameters(2, 4), 0.9, True)
    for _ in range(20):
        split.update(0.01, ResponseParameters(2, 4), 0.9, True)
    assert split.expansion == pytest.approx(whole.expansion, abs=1e-12)
    previous = whole.expansion
    whole.set_target(0.1)
    whole.update(0.05, ResponseParameters(2, 4), 0.9, True)
    assert 0.1 < whole.expansion < previous
    whole.update(10, ResponseParameters(2, 4), 0.9, True)
    assert whole.expansion == 0.1


def test_profiles_share_local_variation_and_remain_fixed() -> None:
    """Nearby same-pigment organs share a dominant timing factor, with small individual noise."""
    geometry = generate_layout(50, 50)
    profiles = generate_response_profiles(geometry)
    assert profiles == generate_response_profiles(geometry)
    assert profiles != generate_response_profiles(geometry, 42)
    groups = defaultdict(list)
    for profile in profiles:
        assert 0.85 * 0.97 <= profile.expansion_scale <= 1.15 * 1.03
        assert 0.85 * 0.97 <= profile.contraction_scale <= 1.15 * 1.03
        groups[profile.group_id].append(profile)
    assert any(len(group) > 1 for group in groups.values())
    for group in groups.values():
        scales = [profile.expansion_scale for profile in group]
        assert max(scales) / min(scales) <= 1.03 / 0.97 + 1e-12
        # The organ multiplier is shared by expansion/contraction; their ratio is group-specific.
        ratios = [profile.expansion_scale / profile.contraction_scale for profile in group]
        assert max(ratios) == pytest.approx(min(ratios))
    assert len({round(profile.expansion_scale, 3) for profile in profiles}) > 100


@pytest.mark.parametrize("enabled", [0, 1, None, "natural"])
def test_mode_switch_validation_is_atomic(enabled: object) -> None:
    """Invalid mode selections leave targets, phase and delays untouched.

    :param enabled: Invalid non-boolean mode selection.
    """
    field = ChromatophoreField(3, 5)
    field.start_dynamic(DynamicDisplay.FLASH)
    before = tuple(astuple(cell) for cell in field.cells)
    with pytest.raises(ValueError):
        field.set_natural_timing(enabled)
    assert not field.natural_timing
    assert tuple(astuple(cell) for cell in field.cells) == before
    assert field.dynamic.phase_seconds == 0


def test_mode_changes_preserve_phase_countdowns_settings_and_hold() -> None:
    """Switching kinetics never issues a target or resumes a held field."""
    field = ChromatophoreField(3, 5, ResponseParameters(4, 4, 0.5))
    field.set_expansion(1)
    field.update(0.2)
    before = tuple(astuple(cell) for cell in field.cells)
    field.set_natural_timing(True)
    assert tuple(astuple(cell) for cell in field.cells) == before
    assert field.response == ResponseParameters(4, 4, 0.5)
    field.start_dynamic(DynamicDisplay.TRAVELLING_WAVE)
    field.update(0.1)
    controller = field.dynamic
    phase = controller.phase_seconds
    field.set_natural_timing(False)
    assert field.dynamic is controller and field.dynamic.phase_seconds == phase
    field.set_natural_timing(True)
    field.hold()
    sizes = tuple(cell.expansion for cell in field.cells)
    field.set_natural_timing(False)
    field.update(2)
    assert tuple(cell.expansion for cell in field.cells) == sizes


def test_natural_dynamic_substeps_and_signal_delay_are_stable() -> None:
    """Natural movement follows delayed targets without introducing per-frame latency."""
    first = ChromatophoreField(5, 7, ResponseParameters(4, 4, 0.5))
    second = ChromatophoreField(5, 7, first.response)
    for field in (first, second):
        field.set_natural_timing(True)
        field.start_dynamic(DynamicDisplay.FLASH, Random(1))
        field.update(0.25)
        assert all(cell.expansion == 0 for cell in field.cells)
    first.update(0.5)
    for _ in range(50):
        second.update(0.01)
    assert tuple(cell.expansion for cell in first.cells) == pytest.approx(
        tuple(cell.expansion for cell in second.cells), abs=1e-12
    )
    assert all(cell.expansion > 0.9 for cell in first.cells)
    assert all(cell._delay_remaining == 0 for cell in first.cells)


@pytest.mark.parametrize("seed", [-1, 2**32, True])
def test_timing_profiles_reject_invalid_seeds(seed: int) -> None:
    """Seed validation matches fixed morphology's unsigned 32-bit contract.

    :param seed: Invalid timing seed.
    """
    with pytest.raises(ValueError):
        generate_response_profiles(generate_layout(2, 2), seed)


@pytest.mark.parametrize(
    "scale,enabled", [(0, True), (-1, True), (float("nan"), True), (float("inf"), True), (1, 1)]
)
def test_invalid_kinetics_leave_cell_state_unchanged(scale: float, enabled: bool) -> None:
    """Validation occurs before consuming delay or changing expansion.

    :param scale: Possibly invalid local multiplier.
    :param enabled: Possibly invalid timing-mode value.
    """
    cell = Chromatophore()
    cell.set_target(1, 0.5)
    before = astuple(cell)
    with pytest.raises(ValueError):
        cell.update(0.1, ResponseParameters(), scale, enabled)
    assert astuple(cell) == before


@pytest.mark.parametrize("geometry", [(), ((float("nan"), 0, 0),), ((0, -1, 0),)])
def test_profiles_reject_invalid_geometry(geometry: tuple) -> None:
    """Do not silently assign plausible timing to invalid organ coordinates.

    :param geometry: Empty geometry or invalid position records.
    """
    from chromatophore_simulator.morphology import OrganGeometry

    organs = tuple(OrganGeometry(x, y, 0.3, pigment) for x, y, pigment in geometry)
    with pytest.raises(ValueError):
        generate_response_profiles(organs)
