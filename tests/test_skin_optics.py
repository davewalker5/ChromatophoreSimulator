"""Physical bounds and colour selectivity of the illustrative RGB skin optics."""

import pytest

from chromatophore_simulator.model import Pigment
from chromatophore_simulator.view import (
    _linear_to_srgb,
    _pigment_reflections,
    _srgb_to_linear,
)


def test_srgb_round_trip_preserves_every_display_channel() -> None:
    """Light conversion must preserve endpoints and avoid display quantisation drift."""
    for channel in range(256):
        assert _linear_to_srgb(_srgb_to_linear(channel)) == channel
    assert _linear_to_srgb(-0.1) == 0
    assert _linear_to_srgb(1.1) == 255


@pytest.mark.parametrize("backing", [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0), (0.2, 0.7, 0.4)])
def test_filtering_stays_bounded_and_does_not_modify_backing(
    backing: tuple[float, ...],
) -> None:
    """Both dark and bright illumination must produce finite, bounded reflections.

    :param backing: Linear RGB light returned by the underlying skin layers.
    """
    before = tuple(backing)
    colours = _pigment_reflections(backing)
    assert set(colours) == set(Pigment)
    assert all(0 <= channel <= 1 for colour in colours.values() for channel in colour)
    assert backing == before


def test_pigments_filter_backing_light_by_colour() -> None:
    """Light pigments pass warm light; dark pigments suppress the backing strongly."""
    dark = _pigment_reflections((0.0, 0.0, 0.0))
    bright = _pigment_reflections((1.0, 1.0, 1.0))
    differences = {
        pigment: tuple(light - shade for light, shade in zip(bright[pigment], dark[pigment]))
        for pigment in Pigment
    }
    yellow = differences[Pigment.YELLOW]
    red = differences[Pigment.RED]
    assert yellow[0] > yellow[1] > yellow[2] > 0
    assert red[0] > red[1] > red[2] > 0
    assert yellow[1] > red[1]
    assert max(differences[Pigment.BLACK]) < min(differences[Pigment.BROWN])
    assert max(differences[Pigment.BROWN]) < yellow[1]
