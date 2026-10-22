"""Fixed local response profiles, independent of target generation and rendering."""

from dataclasses import dataclass
from math import isfinite

from chromatophore_simulator.morphology import DEFAULT_LAYOUT_SEED, PIGMENT_COUNT, OrganGeometry

TIMING_GROUP_SPAN = 3
GROUP_RATE_VARIATION = 0.15
ORGAN_RATE_VARIATION = 0.03
NATURAL_REFERENCE_RATE = 4.0
NATURAL_SETTLING_FACTOR = 4.605170185988092  # ln(100): 99% response in 1 / rate seconds.
NATURAL_SETTLING_THRESHOLD = 0.0001  # Absolute expansion units; snap to an exact target.
_RANDOM_MODULUS = 2**32
_CONTRACTION_SALT = 0xA511E9B3
_ORGAN_SALT = 0x63D83595
_GROUP_X_SALT = 73856093
_GROUP_Y_SALT = 19349663
_GROUP_PIGMENT_SALT = 83492791


@dataclass(frozen=True, slots=True)
class ResponseProfile:
    """Illustrative same-pigment local group membership and dimensionless rate scales."""

    group_id: tuple[int, int, int]
    expansion_scale: float
    contraction_scale: float


def _noise(value: int) -> float:
    """Mix an integer into deterministic noise in [0, 1), matching JavaScript.

    :param value: Integer key, truncated to 32 bits.
    :return: Stable dimensionless pseudo-random value.
    """
    value &= _RANDOM_MODULUS - 1
    value = ((value ^ (value >> 16)) * 0x7FEB352D) & (_RANDOM_MODULUS - 1)
    value = ((value ^ (value >> 15)) * 0x846CA68B) & (_RANDOM_MODULUS - 1)
    return (value ^ (value >> 16)) / _RANDOM_MODULUS


def generate_response_profiles(
    geometry: tuple[OrganGeometry, ...], seed: int = DEFAULT_LAYOUT_SEED
) -> tuple[ResponseProfile, ...]:
    """Assign repeatable timing to nearby organs of the same pigment.

    Group variation is shared within three-spacing squares; small organ variation
    prevents mechanical lockstep. These are illustrative coordination groups, not
    anatomical motor-unit reconstructions. No pattern randomness is consumed.

    :param geometry: Fixed non-empty geometry in logical spacing units.
    :param seed: Unsigned 32-bit integer, normally the field's layout seed.
    :return: Immutable profiles in the same order as geometry.
    :raises ValueError: If the seed, positions or pigment indices are invalid.
    """
    if type(seed) is not int or not 0 <= seed < _RANDOM_MODULUS:
        raise ValueError("Timing seed must be an unsigned 32-bit integer")
    if not geometry or any(
        not isfinite(organ.x)
        or not isfinite(organ.y)
        or organ.x < 0
        or organ.y < 0
        or type(organ.pigment_index) is not int
        or not 0 <= organ.pigment_index < PIGMENT_COUNT
        for organ in geometry
    ):
        raise ValueError("Timing profiles require valid positions and pigment indices")
    profiles = []
    for index, organ in enumerate(geometry):
        group_x, group_y = int(organ.x // TIMING_GROUP_SPAN), int(organ.y // TIMING_GROUP_SPAN)
        key = (
            seed
            ^ ((group_x + 1) * _GROUP_X_SALT)
            ^ ((group_y + 1) * _GROUP_Y_SALT)
            ^ ((organ.pigment_index + 1) * _GROUP_PIGMENT_SALT)
        )
        individual = 1 + ORGAN_RATE_VARIATION * (2 * _noise(seed ^ index ^ _ORGAN_SALT) - 1)
        expansion = 1 + GROUP_RATE_VARIATION * (2 * _noise(key) - 1)
        contraction = 1 + GROUP_RATE_VARIATION * (2 * _noise(key ^ _CONTRACTION_SALT) - 1)
        profiles.append(
            ResponseProfile(
                (group_x, group_y, organ.pigment_index),
                expansion * individual,
                contraction * individual,
            )
        )
    return tuple(profiles)
