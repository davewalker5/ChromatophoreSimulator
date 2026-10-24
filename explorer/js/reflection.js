/** Illustrative angle-dependent optics in one plane through a flat skin normal. */
export const MAXIMUM_ANGLE_DEGREES = 60;
export const ANGLE_PRESETS = Object.freeze([-60, -45, -30, -15, 0, 15, 30, 45, 60]);
// Overlapping regions cover the skin with smoothly varying preferred platelet
// normals. This is an illustrative orientation field, not measured skin relief.
const REFLECTOR_GRID_SIZE = 7;
export const REFLECTOR_CENTRES = Object.freeze(
  Array.from({ length: REFLECTOR_GRID_SIZE ** 2 }, (_, index) =>
    Object.freeze([
      (index % REFLECTOR_GRID_SIZE) / (REFLECTOR_GRID_SIZE - 1),
      Math.floor(index / REFLECTOR_GRID_SIZE) / (REFLECTOR_GRID_SIZE - 1),
    ]),
  ),
);
export const PATCH_NORMAL_DEGREES = Object.freeze(
  REFLECTOR_CENTRES.map(
    ([x, y]) => 25 * Math.sin(Math.PI * (x - 0.5)) * Math.cos(0.6 * Math.PI * (y - 0.5)),
  ),
);
const REFLECTOR_SPREAD_DEGREES = 16;
const DIFFUSE_REFLECTION_FRACTION = 0.08;
const WATER_REFRACTIVE_INDEX = 1.33;
const EFFECTIVE_REFRACTIVE_INDEX = 1.5;
const NORMAL_PEAK_WAVELENGTH_NM = 500;
const VISIBLE_FADE_START_NM = 360;
const VISIBLE_FADE_END_NM = 400;
export const REFERENCE_REFLECTION_COLOUR = Object.freeze([126, 179, 205]);
const WAVELENGTH_COLOURS = Object.freeze([
  Object.freeze([380, Object.freeze([137, 105, 170])]),
  Object.freeze([420, Object.freeze([142, 113, 208])]),
  Object.freeze([460, Object.freeze([106, 143, 215])]),
  Object.freeze([500, REFERENCE_REFLECTION_COLOUR]),
]);

export class ReflectionSettings {
  /**
   * Set signed camera/light angles from the skin normal; positive points right.
   * This affects reflection only, not perspective or diagnostic-disc illumination.
   * @param {number} viewAngle - Degrees in [-60, 60].
   * @param {number} lightAngle - Degrees in [-60, 60].
   * @throws {RangeError} If either angle is non-finite or outside the range.
   */
  constructor(viewAngle = 0, lightAngle = 0) {
    if (
      ![viewAngle, lightAngle].every(
        (angle) => Number.isFinite(angle) && Math.abs(angle) <= MAXIMUM_ANGLE_DEGREES,
      )
    )
      throw new RangeError('Reflection angles must be finite and between -60 and 60 degrees');
    this.viewAngle = viewAngle;
    this.lightAngle = lightAngle;
    Object.freeze(this);
  }
}

/** Convert internal degree values to radians for trigonometry. */
function radians(degrees) {
  return (degrees * Math.PI) / 180;
}

/** Interpolate an illustrative display ramp; this is not spectral colour integration. */
function wavelengthColour(wavelength) {
  if (wavelength <= WAVELENGTH_COLOURS[0][0]) return [...WAVELENGTH_COLOURS[0][1]];
  for (let index = 1; index < WAVELENGTH_COLOURS.length; index++) {
    const [lower, colourA] = WAVELENGTH_COLOURS[index - 1];
    const [upper, colourB] = WAVELENGTH_COLOURS[index];
    if (wavelength <= upper) {
      const fraction = (wavelength - lower) / (upper - lower);
      return colourA.map((a, channel) => a + fraction * (colourB[channel] - a));
    }
  }
  return [...WAVELENGTH_COLOURS.at(-1)[1]];
}

/**
 * Evaluate broad patch lobes and a Snell/Bragg-inspired blue shift once per render.
 * Half-vector alignment selects dispersed reflector normals. Intensity is referenced
 * to zero/zero angles, with oblique-light attenuation and a fade into the ultraviolet.
 * @param {ReflectionSettings} settings - Immutable, validated directions in degrees.
 * @returns {ReadonlyArray<object>} Patch colours and strength multipliers.
 */
export function reflectionResponses(settings = new ReflectionSettings()) {
  const halfAngle = (settings.viewAngle + settings.lightAngle) / 2;
  const incidence = radians((settings.viewAngle - settings.lightAngle) / 2);
  const indexRatio = WATER_REFRACTIVE_INDEX / EFFECTIVE_REFRACTIVE_INDEX;
  const wavelength =
    NORMAL_PEAK_WAVELENGTH_NM * Math.sqrt(Math.max(0, 1 - (indexRatio * Math.sin(incidence)) ** 2));
  const colour = Object.freeze(wavelengthColour(wavelength));
  const visible = Math.max(
    0,
    Math.min(
      1,
      (wavelength - VISIBLE_FADE_START_NM) / (VISIBLE_FADE_END_NM - VISIBLE_FADE_START_NM),
    ),
  );
  const illumination = Math.max(0, Math.cos(radians(settings.lightAngle)));
  return Object.freeze(
    PATCH_NORMAL_DEGREES.map((normal) => {
      const lobe =
        DIFFUSE_REFLECTION_FRACTION +
        (1 - DIFFUSE_REFLECTION_FRACTION) *
          Math.exp(-0.5 * ((halfAngle - normal) / REFLECTOR_SPREAD_DEGREES) ** 2);
      const reference =
        DIFFUSE_REFLECTION_FRACTION +
        (1 - DIFFUSE_REFLECTION_FRACTION) *
          Math.exp(-0.5 * (normal / REFLECTOR_SPREAD_DEGREES) ** 2);
      return Object.freeze({ colour, strength: (lobe / reference) * illumination * visible });
    }),
  );
}
export const DEFAULT_REFLECTION_RESPONSES = reflectionResponses();
