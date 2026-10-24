/** Reproducible fixed organ geometry, in logical cell-spacing units. */
export const DEFAULT_LAYOUT_SEED = 314159;
export const POSITION_JITTER = 0.24;
export const MINIMUM_RADIUS_RATIO = 0.3;
export const MAXIMUM_RADIUS_RATIO = 0.47;
const NEIGHBOUR_CLEARANCE = 0.94;
const RANDOM_MULTIPLIER = 1664525;
const RANDOM_INCREMENT = 1013904223;
const RANDOM_MODULUS = 2 ** 32;
const PIGMENT_COUNT = 4;

/**
 * Create non-overlapping jittered discs with shuffled, balanced pigment identities.
 * Coordinates start at the upper-left. Each organ retains a logical target slot.
 * The isolated integer RNG matches Python and never consumes pattern randomness.
 * @param {number} rows - Positive integer row count.
 * @param {number} columns - Positive integer column count.
 * @param {number} seed - Unsigned 32-bit integer.
 * @returns {ReadonlyArray<Readonly<{x:number,y:number,radiusRatio:number,pigmentIndex:number}>>} Fixed geometry.
 * @throws {RangeError} If dimensions or seed are invalid.
 */
export function generateLayout(rows, columns, seed = DEFAULT_LAYOUT_SEED) {
  if (![rows, columns].every((size) => Number.isInteger(size) && size > 0)) {
    throw new RangeError('Layout dimensions must be positive integers');
  }
  if (!Number.isInteger(seed) || seed < 0 || seed >= RANDOM_MODULUS) {
    throw new RangeError('Layout seed must be an unsigned 32-bit integer');
  }
  let state = seed;
  const random = () => {
    state = (Math.imul(RANDOM_MULTIPLIER, state) + RANDOM_INCREMENT) >>> 0;
    return state / RANDOM_MODULUS;
  };
  const centres = Array.from({ length: rows * columns }, (_, index) => ({
    x: (index % columns) + 0.5 + (2 * random() - 1) * POSITION_JITTER,
    y: Math.floor(index / columns) + 0.5 + (2 * random() - 1) * POSITION_JITTER,
    radiusRatio: MINIMUM_RADIUS_RATIO + random() * (MAXIMUM_RADIUS_RATIO - MINIMUM_RADIUS_RATIO),
  }));
  const pigments = centres.map((_, index) => index % PIGMENT_COUNT);
  for (let index = pigments.length - 1; index > 0; index--) {
    const other = Math.floor(random() * (index + 1));
    [pigments[index], pigments[other]] = [pigments[other], pigments[index]];
  }
  return Object.freeze(
    centres.map(({ x, y, radiusRatio }, index) => {
      const row = Math.floor(index / columns);
      const column = index % columns;
      let radius = Math.min(radiusRatio, x, columns - x, y, rows - y);
      for (let nr = Math.max(0, row - 1); nr < Math.min(rows, row + 2); nr++) {
        for (let nc = Math.max(0, column - 1); nc < Math.min(columns, column + 2); nc++) {
          const neighbour = nr * columns + nc;
          if (neighbour === index) continue;
          const other = centres[neighbour];
          radius = Math.min(
            radius,
            (NEIGHBOUR_CLEARANCE * Math.hypot(x - other.x, y - other.y)) / 2,
          );
        }
      }
      return Object.freeze({ x, y, radiusRatio: radius, pigmentIndex: pigments[index] });
    }),
  );
}
