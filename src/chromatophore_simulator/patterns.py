"""Predefined target fields, independent of animation and rendering."""

from enum import Enum
from math import hypot
from random import Random

BLOCK_SIZE = 6  # Width of checks, bands and mottle sampling intervals, in cells.
SPOT_SPACING = 12
SPOT_RADIUS = 3.5  # Grid-cell units; circular because both axes use the same scale.
UNIFORM_EXPANSION = 0.5


class Pattern(Enum):
    """The seven predefined Stage 3 target patterns."""

    UNIFORM = "Uniform"
    CHECKERBOARD = "Checkerboard"
    HORIZONTAL_BANDS = "Horizontal bands"
    VERTICAL_BANDS = "Vertical bands"
    SPOTS = "Spots"
    RANDOM_MOTTLE = "Random mottle"
    RADIAL_GRADIENT = "Radial gradient"


def generate_targets(
    pattern: Pattern, rows: int, columns: int, random_source: Random
) -> tuple[float, ...]:
    """Generate row-major expansion targets in [0, 1] for a rectangular grid.

    Coordinates start at the upper-left; rows increase downwards. Pattern scale is
    fixed in grid-cell units. Only random mottle consumes random numbers.

    :param pattern: Predefined target arrangement.
    :param rows: Positive integer row count.
    :param columns: Positive integer column count.
    :param random_source: Caller-owned generator; seed it for reproducible mottle.
    :return: One normalised expansion target per cell, stored row by row.
    :raises ValueError: If the pattern or dimensions are invalid.
    """
    if not isinstance(pattern, Pattern):
        raise ValueError("Pattern must be a member of Pattern")
    if any(type(size) is not int or size <= 0 for size in (rows, columns)):
        raise ValueError("Pattern dimensions must be positive integers")
    if pattern is Pattern.RANDOM_MOTTLE:
        return _mottle_targets(rows, columns, random_source)

    centre_row = (rows - 1) / 2
    centre_column = (columns - 1) / 2
    maximum_distance = hypot(centre_row, centre_column)
    targets = []
    for row in range(rows):
        for column in range(columns):
            match pattern:
                case Pattern.UNIFORM:
                    expansion = UNIFORM_EXPANSION
                case Pattern.CHECKERBOARD:
                    # Integer division groups cells into BLOCK_SIZE-wide blocks. Adding
                    # the row and column block indices gives even/odd parity that flips
                    # across either boundary: even blocks expand (1.0), odd contract (0.0).
                    expansion = float((row // BLOCK_SIZE + column // BLOCK_SIZE) % 2 == 0)
                case Pattern.HORIZONTAL_BANDS:
                    # Divide the row index by BLOCK_SIZE to identify its horizontal band.
                    # Even bands expand and odd bands contract; ignoring the column keeps
                    # every cell along a row at the same target expansion.
                    expansion = float((row // BLOCK_SIZE) % 2 == 0)
                case Pattern.VERTICAL_BANDS:
                    # Use the column's band index instead, alternating every BLOCK_SIZE
                    # columns. Ignoring the row makes each band run vertically; float
                    # converts the even-band test from True/False to expansion 1.0/0.0.
                    expansion = float((column // BLOCK_SIZE) % 2 == 0)
                case Pattern.SPOTS:
                    # Repeating local coordinates give each lattice tile a circular spot.
                    offset_row = (row + 0.5) % SPOT_SPACING - SPOT_SPACING / 2
                    offset_column = (column + 0.5) % SPOT_SPACING - SPOT_SPACING / 2
                    expansion = float(hypot(offset_row, offset_column) <= SPOT_RADIUS)
                case Pattern.RADIAL_GRADIENT:
                    # Fade from the geometric centre towards zero at the corners.
                    # A single-cell field has no spatial extent and is fully expanded.
                    distance = hypot(row - centre_row, column - centre_column)
                    expansion = 1.0 - distance / maximum_distance if maximum_distance else 1.0
            targets.append(expansion)
    return tuple(targets)


def _mottle_targets(rows: int, columns: int, random_source: Random) -> tuple[float, ...]:
    """Interpolate coarse random samples into continuous patches of expansion.

    :param rows: Validated field height in cells.
    :param columns: Validated field width in cells.
    :param random_source: Source for the coarse random sample grid.
    :return: Row-major, bilinearly interpolated targets in [0, 1].
    """
    # Choose random expansion levels on a coarse grid, then blend between them.
    # Nearby cells share the same surrounding samples, so they form patches instead
    # of the independent speckle produced by randomising every cell separately.
    # BLOCK_SIZE is the sample spacing in cells: larger spacing produces broader patches.

    # Find the interval containing the last cell on each axis. Add two to include
    # both sample endpoints, ensuring even edge cells have neighbours to blend between.
    sample_rows = (rows - 1) // BLOCK_SIZE + 2
    sample_columns = (columns - 1) // BLOCK_SIZE + 2

    # Samples lie in [0, 1). The caller's generator makes the pattern reproducible
    # when seeded, while successive calls with that generator produce fresh mottles.
    samples = [[random_source.random() for _ in range(sample_columns)] for _ in range(sample_rows)]
    targets = []
    for row in range(rows):
        # divmod identifies the upper sample row and the cell's offset below it.
        # Dividing that offset by the spacing gives a blend fraction: 0 is at the
        # upper sample, and 0.5 is halfway towards the lower sample.
        sample_row, row_remainder = divmod(row, BLOCK_SIZE)
        row_fraction = row_remainder / BLOCK_SIZE
        for column in range(columns):
            # Repeat horizontally to locate the left sample and fraction towards
            # the right sample. Together these locate four samples around this cell.
            sample_column, column_remainder = divmod(column, BLOCK_SIZE)
            column_fraction = column_remainder / BLOCK_SIZE

            # First blend left-to-right along each of the two sample rows. Weights
            # (1 - fraction) and fraction sum to one; at 0.5 this is a simple average.
            upper = (
                samples[sample_row][sample_column] * (1 - column_fraction)
                + samples[sample_row][sample_column + 1] * column_fraction
            )
            lower = (
                samples[sample_row + 1][sample_column] * (1 - column_fraction)
                + samples[sample_row + 1][sample_column + 1] * column_fraction
            )
            # Then blend those results top-to-bottom: this is bilinear interpolation.
            # The result stays within the surrounding samples' range (hence [0, 1])
            # and changes continuously between them, giving smoothly varying patches.
            # Append targets only; the model later animates each cell towards its value.
            targets.append(upper * (1 - row_fraction) + lower * row_fraction)
    return tuple(targets)
