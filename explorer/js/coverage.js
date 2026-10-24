/** Analytical disc/rectangle integration in logical cell-spacing units. */

/** Signed circle area from its centre to a rectangle corner; radius must be positive. */
function quadrantArea(x, y, radius) {
  const width = Math.min(Math.abs(x), radius);
  const height = Math.min(Math.abs(y), radius);
  const sign = x < 0 !== y < 0 ? -1 : 1;
  if (width * width + height * height <= radius * radius) return sign * width * height;
  const transition = Math.sqrt(Math.max(0, radius * radius - height * height));
  const upper = width * Math.sqrt(Math.max(0, radius * radius - width * width));
  const lower = transition * height;
  const arc = radius * radius * (Math.asin(width / radius) - Math.asin(transition / radius));
  return sign * (height * transition + (upper - lower + arc) / 2);
}

/**
 * Integrate a disc within an axis-aligned rectangle without sampling raster pixels.
 * @param {number} x - Horizontal circle centre.
 * @param {number} y - Vertical circle centre.
 * @param {number} radius - Non-negative radius, in coordinate units.
 * @param {number[]} bounds - Rectangle [left, top, right, bottom].
 * @returns {number} Intersection area in squared coordinate units.
 * @throws {RangeError} If coordinates are non-finite, bounds inverted or radius negative.
 */
export function circleRectangleArea(x, y, radius, bounds) {
  if (
    !Array.isArray(bounds) ||
    bounds.length !== 4 ||
    ![x, y, radius, ...bounds].every(Number.isFinite)
  ) {
    throw new RangeError('Coverage coordinates must be finite');
  }
  const [left, top, right, bottom] = bounds;
  if (radius < 0 || right < left || bottom < top) {
    throw new RangeError('Radius and rectangle dimensions must be non-negative');
  }
  if (
    radius === 0 ||
    right <= x - radius ||
    left >= x + radius ||
    bottom <= y - radius ||
    top >= y + radius
  )
    return 0;
  if (left <= x - radius && right >= x + radius && top <= y - radius && bottom >= y + radius)
    return Math.PI * radius * radius;
  const area =
    quadrantArea(right - x, bottom - y, radius) -
    quadrantArea(left - x, bottom - y, radius) -
    quadrantArea(right - x, top - y, radius) +
    quadrantArea(left - x, top - y, radius);
  return Math.max(0, Math.min(area, Math.PI * radius * radius, (right - left) * (bottom - top)));
}
