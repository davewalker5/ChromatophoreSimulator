"""Analytical circle coverage for integrating irregular organs without raster aliasing."""

from math import asin, isfinite, pi, sqrt


def _quadrant_area(x: float, y: float, radius: float) -> float:
    """Integrate a circle from its centre to signed rectangle coordinates.

    :param x: Signed horizontal offset in the circle's length units.
    :param y: Signed vertical offset in the circle's length units.
    :param radius: Positive circle radius in the same units.
    :return: Signed area for inclusion-exclusion across four rectangle corners.
    """
    width, height = min(abs(x), radius), min(abs(y), radius)
    sign = -1 if (x < 0) != (y < 0) else 1
    if width * width + height * height <= radius * radius:
        return sign * width * height
    transition = sqrt(max(0.0, radius * radius - height * height))
    # Beyond transition, the circular arc rather than rectangle height bounds area.
    upper = width * sqrt(max(0.0, radius * radius - width * width))
    lower = transition * height
    arc = radius * radius * (asin(width / radius) - asin(transition / radius))
    return sign * (height * transition + (upper - lower + arc) / 2)


def circle_rectangle_area(
    x: float, y: float, radius: float, bounds: tuple[float, float, float, float]
) -> float:
    """Return exact disc area within an axis-aligned rectangle.

    :param x: Circle centre's horizontal coordinate.
    :param y: Circle centre's vertical coordinate.
    :param radius: Non-negative radius, in the same units as the coordinates.
    :param bounds: Rectangle (left, top, right, bottom), allowing zero area.
    :return: Intersection area in squared coordinate units.
    :raises ValueError: If coordinates are non-finite, bounds inverted or radius negative.
    """
    left, top, right, bottom = bounds
    if not all(isfinite(value) for value in (x, y, radius, *bounds)):
        raise ValueError("Coverage coordinates must be finite")
    if radius < 0 or right < left or bottom < top:
        raise ValueError("Radius and rectangle dimensions must be non-negative")
    if radius == 0 or right <= x - radius or left >= x + radius:
        return 0.0
    if bottom <= y - radius or top >= y + radius:
        return 0.0
    if left <= x - radius and right >= x + radius and top <= y - radius and bottom >= y + radius:
        return pi * radius * radius
    area = (
        _quadrant_area(right - x, bottom - y, radius)
        - _quadrant_area(left - x, bottom - y, radius)
        - _quadrant_area(right - x, top - y, radius)
        + _quadrant_area(left - x, top - y, radius)
    )
    return max(0.0, min(area, pi * radius * radius, (right - left) * (bottom - top)))
