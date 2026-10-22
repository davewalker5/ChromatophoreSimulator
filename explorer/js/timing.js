/** Fixed illustrative local response profiles; no frame or pattern randomness. */
import { DEFAULT_LAYOUT_SEED } from './morphology.js';
export const TIMING_GROUP_SPAN = 3;
export const GROUP_RATE_VARIATION = 0.15;
export const ORGAN_RATE_VARIATION = 0.03;
export const NATURAL_REFERENCE_RATE = 4;
export const NATURAL_SETTLING_FACTOR = 4.605170185988092;
export const NATURAL_SETTLING_THRESHOLD = 0.0001;
const RANDOM_MODULUS = 2 ** 32;
const CONTRACTION_SALT = 0xa511e9b3;
const ORGAN_SALT = 0x63d83595;
const GROUP_X_SALT = 73856093;
const GROUP_Y_SALT = 19349663;
const GROUP_PIGMENT_SALT = 83492791;
const PIGMENT_COUNT = 4;

/** Mix a 32-bit integer key into stable dimensionless noise in [0, 1). */
function noise(value) {
  value >>>= 0;
  value = Math.imul(value ^ (value >>> 16), 0x7feb352d) >>> 0;
  value = Math.imul(value ^ (value >>> 15), 0x846ca68b) >>> 0;
  return ((value ^ (value >>> 16)) >>> 0) / RANDOM_MODULUS;
}

/**
 * Create shared local timing with small individual differences, matching Python.
 * These three-spacing same-pigment groups are not measured anatomical motor units.
 * @param {ReadonlyArray<object>} geometry - Fixed positions and pigment indices.
 * @param {number} seed - Unsigned 32-bit layout seed.
 * @returns {ReadonlyArray<object>} Immutable group membership and rate scales.
 * @throws {RangeError} If geometry or seed is invalid.
 */
export function generateResponseProfiles(geometry, seed = DEFAULT_LAYOUT_SEED) {
  if (!Number.isInteger(seed) || seed < 0 || seed >= RANDOM_MODULUS)
    throw new RangeError('Timing seed must be an unsigned 32-bit integer');
  if (
    !geometry.length ||
    !geometry.every(
      (organ) =>
        Number.isFinite(organ.x) &&
        Number.isFinite(organ.y) &&
        organ.x >= 0 &&
        organ.y >= 0 &&
        Number.isInteger(organ.pigmentIndex) &&
        organ.pigmentIndex >= 0 &&
        organ.pigmentIndex < PIGMENT_COUNT,
    )
  )
    throw new RangeError('Timing profiles require valid positions and pigment indices');
  return Object.freeze(
    geometry.map((organ, index) => {
      const groupX = Math.floor(organ.x / TIMING_GROUP_SPAN);
      const groupY = Math.floor(organ.y / TIMING_GROUP_SPAN);
      const key =
        seed ^
        Math.imul(groupX + 1, GROUP_X_SALT) ^
        Math.imul(groupY + 1, GROUP_Y_SALT) ^
        Math.imul(organ.pigmentIndex + 1, GROUP_PIGMENT_SALT);
      const individual = 1 + ORGAN_RATE_VARIATION * (2 * noise(seed ^ index ^ ORGAN_SALT) - 1);
      const expansion = 1 + GROUP_RATE_VARIATION * (2 * noise(key) - 1);
      const contraction = 1 + GROUP_RATE_VARIATION * (2 * noise(key ^ CONTRACTION_SALT) - 1);
      return Object.freeze({
        groupId: Object.freeze([groupX, groupY, organ.pigmentIndex]),
        expansionScale: expansion * individual,
        contractionScale: contraction * individual,
      });
    }),
  );
}
