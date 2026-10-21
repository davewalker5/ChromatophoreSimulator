"""Reproducible organ geometry in logical cell-spacing units, independent of animation."""

from dataclasses import dataclass
from math import hypot

DEFAULT_LAYOUT_SEED = 314159
POSITION_JITTER = 0.24
MINIMUM_RADIUS_RATIO = 0.30
MAXIMUM_RADIUS_RATIO = 0.47
NEIGHBOUR_CLEARANCE = 0.94
RANDOM_MULTIPLIER = 1664525
RANDOM_INCREMENT = 1013904223
RANDOM_MODULUS = 2**32
PIGMENT_COUNT = 4


@dataclass(frozen=True, slots=True)
class OrganGeometry:
    """Fixed centre, maximum radius and pigment index for one logical cell.

    Coordinates start at the patch's upper-left and use cell spacing as the unit.
    Factory-generated radii keep discs inside the patch and clear of neighbours.
    """

    x: float
    y: float
    radius_ratio: float
    pigment_index: int


class _LayoutRandom:
    """Small integer generator shared exactly with the JavaScript implementation."""

    def __init__(self, seed: int) -> None:
        """Initialise isolated layout randomness.

        :param seed: Validated unsigned 32-bit integer.
        """
        self.state = seed

    def random(self) -> float:
        """Return the next deterministic value in [0, 1)."""
        self.state = (RANDOM_MULTIPLIER * self.state + RANDOM_INCREMENT) % RANDOM_MODULUS
        return self.state / RANDOM_MODULUS


def generate_layout(
    rows: int, columns: int, seed: int = DEFAULT_LAYOUT_SEED
) -> tuple[OrganGeometry, ...]:
    """Create a balanced pigment population with jittered centres and variable radii.

    One organ remains associated with each logical target slot. Only adjacent slots
    can approach within twice the largest radius, so local distance checks suffice.
    Limiting each radius to less than half every neighbour distance prevents overlap
    without a drawing-order dependency. Layout randomness never consumes pattern RNG.

    :param rows: Positive logical row count.
    :param columns: Positive logical column count.
    :param seed: Unsigned 32-bit integer; identical inputs reproduce the same layout.
    :return: Immutable geometry in logical row-major target order.
    :raises ValueError: If dimensions or seed are invalid.
    """
    if any(type(size) is not int or size <= 0 for size in (rows, columns)):
        raise ValueError("Layout dimensions must be positive integers")
    if type(seed) is not int or not 0 <= seed < RANDOM_MODULUS:
        raise ValueError("Layout seed must be an unsigned 32-bit integer")
    source = _LayoutRandom(seed)
    centres = tuple(
        (
            column + 0.5 + (2 * source.random() - 1) * POSITION_JITTER,
            row + 0.5 + (2 * source.random() - 1) * POSITION_JITTER,
            MINIMUM_RADIUS_RATIO + source.random() * (MAXIMUM_RADIUS_RATIO - MINIMUM_RADIUS_RATIO),
        )
        for row in range(rows)
        for column in range(columns)
    )
    pigments = [index % PIGMENT_COUNT for index in range(rows * columns)]
    for index in range(len(pigments) - 1, 0, -1):
        other = int(source.random() * (index + 1))
        pigments[index], pigments[other] = pigments[other], pigments[index]
    geometry = []
    for index, (x, y, desired_radius) in enumerate(centres):
        row, column = divmod(index, columns)
        radius = min(desired_radius, x, columns - x, y, rows - y)
        for neighbour_row in range(max(0, row - 1), min(rows, row + 2)):
            for neighbour_column in range(max(0, column - 1), min(columns, column + 2)):
                neighbour = neighbour_row * columns + neighbour_column
                if neighbour == index:
                    continue
                other_x, other_y, _ = centres[neighbour]
                radius = min(radius, NEIGHBOUR_CLEARANCE * hypot(x - other_x, y - other_y) / 2)
        geometry.append(OrganGeometry(x, y, radius, pigments[index]))
    return tuple(geometry)
