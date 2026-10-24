"""Define repeatable local variations in chromatophore response timing.

Natural timing gives nearby organs of the same pigment a shared tendency to
expand or contract faster or slower, with a smaller individual variation so they
do not move in mechanical lockstep. Groups are defined by three-cell-spacing
squares and pigment identity. They are illustrative coordination groups, not
reconstructions of anatomical motor units or connections between individual organs.

Each organ receives an immutable profile containing its group identity and two
dimensionless rate multipliers: one for expansion and one for contraction. A value
of 1 leaves the selected rate unchanged; values above or below 1 make the response
faster or slower. Group variation is up to 15% either way, multiplied by an
individual variation of up to 3%. Expansion and contraction use different group
noise keys but share the same individual multiplier.

Profiles are derived from fixed geometry, its ordering and a seed using integer
mixing that matches the JavaScript implementation. They consume no pattern random
numbers and do not change from frame to frame. Sharing a group influences response
speed only: it does not force organs to share targets, start together or exchange
signals. Target generation and response delays remain the model's responsibility.

This module also defines the natural-response calibration used by the model's
exponential approach to a target. With a profile multiplier of 1, the settling
factor gives 99% completion of the initial difference in 1 / rate seconds; a small
absolute threshold lets the model finish at the exact target. This module does
not advance animation, modify organ state or render the skin.
"""

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
    # Reject booleans as well as out-of-range seeds: bool is an int subclass,
    # but is not a meaningful layout seed. The 32-bit range matches JavaScript.
    if type(seed) is not int or not 0 <= seed < _RANDOM_MODULUS:
        raise ValueError("Timing seed must be an unsigned 32-bit integer")

    # Group coordinates require finite, non-negative positions, and pigment
    # identity is part of each group key. Validate the entire input before
    # constructing profiles so an invalid organ cannot produce partial results.
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
        # Floor division assigns actual organ centres to fixed spatial squares,
        # rather than grouping by their row-major indices. Pigment is included
        # below so different pigment types in the same square stay independent.
        group_x, group_y = int(organ.x // TIMING_GROUP_SPAN), int(organ.y // TIMING_GROUP_SPAN)

        # Mix the seed, square coordinates and pigment into a repeatable key.
        # Distinct multipliers separate the three components; the +1 offsets
        # ensure that zero-valued coordinates or pigment indices still contribute.
        # This is a noise key, not a unique identifier: group_id stores membership.
        key = (
            seed
            ^ ((group_x + 1) * _GROUP_X_SALT)
            ^ ((group_y + 1) * _GROUP_Y_SALT)
            ^ ((organ.pigment_index + 1) * _GROUP_PIGMENT_SALT)
        )

        # Map noise from [0, 1) to [-1, 1), then scale around a neutral value of 1.
        # The geometry index gives each organ a stable personal adjustment without
        # consuming random values from patterns or depending on iteration history.
        individual = 1 + ORGAN_RATE_VARIATION * (2 * _noise(seed ^ index ^ _ORGAN_SALT) - 1)

        # Same-group organs share these larger adjustments. A separate contraction
        # key allows a group to expand quickly yet contract slowly, or vice versa,
        # instead of assigning one speed tendency to both directions.
        expansion = 1 + GROUP_RATE_VARIATION * (2 * _noise(key) - 1)
        contraction = 1 + GROUP_RATE_VARIATION * (2 * _noise(key ^ _CONTRACTION_SALT) - 1)

        # Multiplication preserves the group's tendency while adding slight organ
        # variation (combined scales span approximately 0.825 to 1.185). Store
        # profiles in geometry order so the model can pair them with their organs.
        profiles.append(
            ResponseProfile(
                (group_x, group_y, organ.pigment_index),
                expansion * individual,
                contraction * individual,
            )
        )
    return tuple(profiles)
