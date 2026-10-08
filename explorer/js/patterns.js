/** Static target fields. Coordinates start at the upper-left and use cell units. */
export const Pattern = Object.freeze({
  UNIFORM: 'Uniform',
  CHECKERBOARD: 'Checkerboard',
  HORIZONTAL_BANDS: 'Horizontal bands',
  VERTICAL_BANDS: 'Vertical bands',
  SPOTS: 'Spots',
  RANDOM_MOTTLE: 'Random mottle',
  RADIAL_GRADIENT: 'Radial gradient',
});
export const BLOCK_SIZE = 6;
export const SPOT_SPACING = 12;
export const SPOT_RADIUS = 3.5;

/**
 * Reject dimensions which cannot describe a non-empty rectangular field.
 * @param {number} rows - Height in cells.
 * @param {number} columns - Width in cells.
 * @throws {RangeError} If either dimension is not a positive integer.
 */
export function validateDimensions(rows, columns) {
  if (![rows, columns].every((size) => Number.isInteger(size) && size > 0)) {
    throw new RangeError('Field dimensions must be positive integers');
  }
}

/**
 * Calculate targets independently of cell state and drawing.
 * @param {string} pattern - A member of Pattern.
 * @param {number} rows - Positive field height.
 * @param {number} columns - Positive field width.
 * @param {{random: function(): number}} randomSource - Caller-owned generator.
 * @returns {Float64Array} Row-major expansion targets in [0, 1].
 * @throws {RangeError} If the pattern or dimensions are invalid.
 */
export function generateTargets(pattern, rows, columns, randomSource) {
  validateDimensions(rows, columns);
  if (!Object.values(Pattern).includes(pattern)) throw new RangeError('Unknown pattern');
  if (pattern === Pattern.RANDOM_MOTTLE) return mottleTargets(rows, columns, randomSource);
  const centreRow = (rows - 1) / 2;
  const centreColumn = (columns - 1) / 2;
  const maximumDistance = Math.hypot(centreRow, centreColumn);
  const targets = new Float64Array(rows * columns);
  for (let row = 0; row < rows; row++) {
    for (let column = 0; column < columns; column++) {
      let expansion;
      switch (pattern) {
        case Pattern.UNIFORM:
          expansion = 0.5;
          break;
        case Pattern.CHECKERBOARD:
          // Block-index parity flips at either boundary, giving six-cell checks.
          expansion = Number(
            (Math.floor(row / BLOCK_SIZE) + Math.floor(column / BLOCK_SIZE)) % 2 === 0,
          );
          break;
        case Pattern.HORIZONTAL_BANDS:
          expansion = Number(Math.floor(row / BLOCK_SIZE) % 2 === 0);
          break;
        case Pattern.VERTICAL_BANDS:
          expansion = Number(Math.floor(column / BLOCK_SIZE) % 2 === 0);
          break;
        case Pattern.SPOTS: {
          // Local tile coordinates put a circular spot in each repeating square.
          const y = ((row + 0.5) % SPOT_SPACING) - SPOT_SPACING / 2;
          const x = ((column + 0.5) % SPOT_SPACING) - SPOT_SPACING / 2;
          expansion = Number(Math.hypot(y, x) <= SPOT_RADIUS);
          break;
        }
        case Pattern.RADIAL_GRADIENT:
          // The one-cell case has no distance to normalise and is fully expanded.
          expansion = maximumDistance
            ? 1 - Math.hypot(row - centreRow, column - centreColumn) / maximumDistance
            : 1;
          break;
      }
      targets[row * columns + column] = expansion;
    }
  }
  return targets;
}

/**
 * Blend coarse random samples into broad patches, not independent speckle.
 * @param {number} rows - Validated height in cells.
 * @param {number} columns - Validated width in cells.
 * @param {{random: function(): number}} source - Generator used only for samples.
 * @returns {Float64Array} Bilinearly interpolated row-major targets.
 */
function mottleTargets(rows, columns, source) {
  // Two endpoints beyond the last interval keep edge cells inside a sample tile.
  const sampleRows = Math.floor((rows - 1) / BLOCK_SIZE) + 2;
  const sampleColumns = Math.floor((columns - 1) / BLOCK_SIZE) + 2;
  const samples = Float64Array.from({ length: sampleRows * sampleColumns }, () => source.random());
  const targets = new Float64Array(rows * columns);
  for (let row = 0; row < rows; row++) {
    const sampleRow = Math.floor(row / BLOCK_SIZE);
    const vertical = (row % BLOCK_SIZE) / BLOCK_SIZE;
    for (let column = 0; column < columns; column++) {
      const sampleColumn = Math.floor(column / BLOCK_SIZE);
      const horizontal = (column % BLOCK_SIZE) / BLOCK_SIZE;
      const index = sampleRow * sampleColumns + sampleColumn;
      // First interpolate along both sample rows, then between those results.
      // Each pair of weights sums to one, so expansion remains within [0, 1].
      const upper = samples[index] * (1 - horizontal) + samples[index + 1] * horizontal;
      const lower =
        samples[index + sampleColumns] * (1 - horizontal) +
        samples[index + sampleColumns + 1] * horizontal;
      targets[row * columns + column] = upper * (1 - vertical) + lower * vertical;
    }
  }
  return targets;
}
