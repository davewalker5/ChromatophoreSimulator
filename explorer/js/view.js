/** Canvas rendering reads state only; drawing never changes targets or time. */
import { circleRectangleArea } from './coverage.js';
import { Pigment } from './model.js';

export const LOGICAL_SIZE = 550;
export const SKIN_COLOUR = Object.freeze([235, 232, 220]);
// Common cuttlefish-inspired sRGB palette, with neutral daylight (D65) as the target.
// Illustrative colours rather than measured reflectance; Black represents dark brown.
export const IRIDOPHORE_COLOUR = Object.freeze([126, 179, 205]);
export const IRIDOPHORE_STRENGTH = 0.28;

// Illustrative mantle patches, not an anatomical map. Coordinates are normalised.
export const IRIDOPHORE_PATCHES = Object.freeze([
  Object.freeze([0.24, 0.3, 0.15, 0.24]),
  Object.freeze([0.76, 0.36, 0.13, 0.22]),
  Object.freeze([0.48, 0.78, 0.22, 0.12]),
]);

export function iridophoreBase(strength = IRIDOPHORE_STRENGTH, x = 0.5, y = 0.5) {
  const patch = Math.max(
    ...IRIDOPHORE_PATCHES.map(([cx, cy, rx, ry]) =>
      Math.exp(-2 * (((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2)),
    ),
  );
  return SKIN_COLOUR.map((base, channel) =>
    roundEven(base + strength * patch * (IRIDOPHORE_COLOUR[channel] - base)),
  );
}
export const PIGMENT_COLOURS = Object.freeze({
  [Pigment.YELLOW]: Object.freeze([190, 145, 52]),
  [Pigment.RED]: Object.freeze([155, 74, 46]),
  [Pigment.BROWN]: Object.freeze([85, 56, 40]),
  [Pigment.BLACK]: Object.freeze([43, 34, 29]),
});
// Illustrative effective round-trip transmission of linear RGB light, not spectra.
export const PIGMENT_TRANSMISSION = Object.freeze({
  [Pigment.YELLOW]: Object.freeze([0.55, 0.35, 0.04]),
  [Pigment.RED]: Object.freeze([0.35, 0.05, 0.02]),
  [Pigment.BROWN]: Object.freeze([0.07, 0.04, 0.02]),
  [Pigment.BLACK]: Object.freeze([0.015, 0.01, 0.008]),
});
const SRGB_CHANNEL_MAXIMUM = 255;
const SRGB_LINEAR_THRESHOLD = 0.04045;
const LINEAR_SRGB_THRESHOLD = 0.0031308;
const SRGB_LINEAR_SCALE = 12.92;
const SRGB_OFFSET = 0.055;
const SRGB_SCALE = 1.055;
const SRGB_EXPONENT = 2.4;

/** Decode an internal 0–255 sRGB channel to linear intensity in [0, 1]. */
function srgbToLinear(channel) {
  const value = channel / SRGB_CHANNEL_MAXIMUM;
  return value <= SRGB_LINEAR_THRESHOLD
    ? value / SRGB_LINEAR_SCALE
    : ((value + SRGB_OFFSET) / SRGB_SCALE) ** SRGB_EXPONENT;
}

/** Encode internal linear light intensity to a clamped 0–255 sRGB channel. */
function linearToSrgb(intensity) {
  const value = Math.max(0, Math.min(1, intensity));
  const encoded =
    value <= LINEAR_SRGB_THRESHOLD
      ? value * SRGB_LINEAR_SCALE
      : SRGB_SCALE * value ** (1 / SRGB_EXPONENT) - SRGB_OFFSET;
  return roundEven(encoded * SRGB_CHANNEL_MAXIMUM);
}

/**
 * Calculate covered-area reflection using a bounded mixture of pigment and backing light.
 * @param {number[]} backing - Three linear RGB intensities in [0, 1].
 * @returns {Object<string, number[]>} Linear RGB reflection for each pigment.
 * @throws {RangeError} If backing is not three finite intensities in [0, 1].
 */
export function pigmentReflections(backing) {
  if (
    !Array.isArray(backing) ||
    backing.length !== 3 ||
    !backing.every((value) => Number.isFinite(value) && value >= 0 && value <= 1)
  ) {
    throw new RangeError('Backing must contain three linear RGB intensities in [0, 1]');
  }
  return Object.fromEntries(
    Object.entries(PIGMENT_COLOURS).map(([pigment, colour]) => [
      pigment,
      colour.map((channel, index) => {
        const transmission = PIGMENT_TRANSMISSION[pigment][index];
        return srgbToLinear(channel) * (1 - transmission) + backing[index] * transmission;
      }),
    ]),
  );
}

export const MINIMUM_RADIUS = 0.8;
export const SKIN_SAMPLE_SPAN = 2;
export const SKIN_CONTRAST = 2;
export const SKIN_REFERENCE_RADIUS_RATIO = 0.45;
export const SKIN_SHARPNESS = 2.0;
export const ViewMode = Object.freeze({ CHROMATOPHORES: 'Chromatophores', SKIN: 'Skin' });

/**
 * Round ties to even, matching Python's round rather than JS's half-up rule.
 * @param {number} value - Channel value before clamping.
 * @returns {number} Nearest integer, choosing an even integer at an exact tie.
 */
export function roundEven(value) {
  const lower = Math.floor(value);
  if (value - lower === 0.5) return lower % 2 === 0 ? lower : lower + 1;
  return Math.round(value);
}

/**
 * Calibrate maximum pigment area against the former regular layout.
 * The fixed, global gain preserves local variation without tracking animation brightness.
 * @param {import('./model.js').ChromatophoreField} field - Non-empty, valid organ field.
 * @returns {number} Dimensionless integrated-coverage multiplier.
 * @throws {RangeError} If geometry is empty or contains invalid maximum radii.
 */
export function skinCoverageGain(field) {
  if (
    !field.geometry.length ||
    !field.geometry.every((organ) => Number.isFinite(organ.radiusRatio) && organ.radiusRatio > 0)
  ) {
    throw new RangeError('Skin calibration requires positive, finite organ radii');
  }
  const maximumArea = field.geometry.reduce((sum, organ) => sum + organ.radiusRatio ** 2, 0);
  return (field.geometry.length * SKIN_REFERENCE_RADIUS_RATIO ** 2) / maximumArea;
}

/**
 * Calculate area-weighted skin samples without reducing a raster of circles.
 * @param {import('./model.js').ChromatophoreField} field - State to display.
 * @param {Uint8ClampedArray} [pixels] - Optional reusable RGBA destination.
 * @returns {{width: number, height: number, pixels: Uint8ClampedArray}} Sample image.
 */
export function skinSamples(field, pixels, iridophoreStrength = IRIDOPHORE_STRENGTH) {
  const width = Math.ceil(field.columns / SKIN_SAMPLE_SPAN);
  const height = Math.ceil(field.rows / SKIN_SAMPLE_SPAN);
  const destination = pixels ?? new Uint8ClampedArray(width * height * 4);
  const spacing = LOGICAL_SIZE / Math.max(field.rows, field.columns);
  const coverageGain = skinCoverageGain(field);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const left = x * SKIN_SAMPLE_SPAN;
      const top = y * SKIN_SAMPLE_SPAN;
      const right = Math.min(left + SKIN_SAMPLE_SPAN, field.columns);
      const bottom = Math.min(top + SKIN_SAMPLE_SPAN, field.rows);
      const base = iridophoreBase(
        iridophoreStrength,
        (left + right) / (2 * field.columns),
        (top + bottom) / (2 * field.rows),
      ).map(srgbToLinear);
      const reflections = pigmentReflections(base);
      const areas = Object.fromEntries(Object.values(Pigment).map((pigment) => [pigment, 0]));
      // Include the adjacent logical slots: displaced discs can cross sample boundaries.
      for (let row = Math.max(0, top - 1); row < Math.min(field.rows, bottom + 1); row++) {
        for (
          let column = Math.max(0, left - 1);
          column < Math.min(field.columns, right + 1);
          column++
        ) {
          const index = row * field.columns + column;
          const cell = field.cells[index];
          const organ = field.geometry[index];
          const minimumRadius = Math.min(MINIMUM_RADIUS / spacing, organ.radiusRatio);
          const radius = minimumRadius + cell.expansion * (organ.radiusRatio - minimumRadius);
          areas[cell.pigment] += circleRectangleArea(organ.x, organ.y, radius, [
            left,
            top,
            right,
            bottom,
          ]);
        }
      }
      const weights = Object.fromEntries(
        Object.entries(areas).map(([pigment, area]) => [
          pigment,
          (SKIN_CONTRAST * coverageGain * area) / ((right - left) * (bottom - top)),
        ]),
      );
      const totalWeight = Object.values(weights).reduce((sum, weight) => sum + weight, 0);
      const normalisation = Math.max(1, totalWeight);
      const offset = (y * width + x) * 4;
      for (let channel = 0; channel < 3; channel++) {
        let light = base[channel] * Math.max(0, 1 - totalWeight);
        for (const pigment of Object.values(Pigment)) {
          light += (reflections[pigment][channel] * weights[pigment]) / normalisation;
        }
        destination[offset + channel] = linearToSrgb(light);
      }
      destination[offset + 3] = 255;
    }
  }
  return { width, height, pixels: destination };
}

/** Strengthen integrated pattern edges with a clamped 3 × 3 unsharp mask. */
export function sharpenSkin(pixels, width, height) {
  const source = pixels.slice();
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      for (let channel = 0; channel < 3; channel++) {
        let blurred = 0;
        for (let dy = -1; dy <= 1; dy++) {
          for (let dx = -1; dx <= 1; dx++) {
            const sx = Math.max(0, Math.min(width - 1, x + dx));
            const sy = Math.max(0, Math.min(height - 1, y + dy));
            blurred += source[(sy * width + sx) * 4 + channel];
          }
        }
        const offset = (y * width + x) * 4 + channel;
        pixels[offset] = roundEven(
          source[offset] + SKIN_SHARPNESS * (source[offset] - blurred / 9),
        );
      }
    }
  }
  return pixels;
}

export class FieldView {
  /**
   * Prepare drawing surfaces and a fixed logical coordinate system.
   * @param {HTMLCanvasElement} canvas - Visible drawing surface.
   * @throws {Error} If Canvas 2D is unavailable.
   */
  constructor(canvas) {
    this.canvas = canvas;
    this.context = canvas.getContext('2d', { alpha: false });
    this.samples = document.createElement('canvas');
    this.sampleContext = this.samples.getContext('2d', { alpha: false });
    if (!this.context || !this.sampleContext) throw new Error('Canvas 2D is unavailable');
    this.mode = ViewMode.CHROMATOPHORES;
    this.sampleImage = null;
  }

  /**
   * Render a field with device-pixel resolution, preserving logical disc radii.
   * @param {import('./model.js').ChromatophoreField} field - Read-only model state.
   */
  draw(field) {
    const size = Math.max(
      1,
      Math.round(this.canvas.getBoundingClientRect().width * (window.devicePixelRatio || 1)),
    );
    if (this.canvas.width !== size || this.canvas.height !== size) {
      this.canvas.width = size;
      this.canvas.height = size;
    }
    const context = this.context;
    context.setTransform(size / LOGICAL_SIZE, 0, 0, size / LOGICAL_SIZE, 0, 0);
    context.fillStyle = `rgb(${SKIN_COLOUR.join(',')})`;
    context.fillRect(0, 0, LOGICAL_SIZE, LOGICAL_SIZE);
    const spacing = LOGICAL_SIZE / Math.max(field.rows, field.columns);
    const left = (LOGICAL_SIZE - field.columns * spacing) / 2;
    const top = (LOGICAL_SIZE - field.rows * spacing) / 2;
    if (this.mode === ViewMode.SKIN) {
      this.drawSkin(field, left, top, spacing);
      return;
    }
    // Batch by pigment to avoid thousands of fill calls. Discs do not overlap,
    // so batching preserves the appearance without introducing layer ordering.
    for (const [pigment, colour] of Object.entries(PIGMENT_COLOURS)) {
      context.fillStyle = `rgb(${colour.join(',')})`;
      context.beginPath();
      for (let index = 0; index < field.cells.length; index++) {
        const cell = field.cells[index];
        if (cell.pigment !== pigment) continue;
        const organ = field.geometry[index];
        const x = left + organ.x * spacing;
        const y = top + organ.y * spacing;
        const maximum = organ.radiusRatio * spacing;
        const minimum = Math.min(MINIMUM_RADIUS, maximum);
        const radius = minimum + cell.expansion * (maximum - minimum);
        context.moveTo(x + radius, y);
        context.arc(x, y, radius, 0, Math.PI * 2);
      }
      context.fill();
    }
  }

  /**
   * Enlarge the small coverage image with smooth interpolation.
   * @param {import('./model.js').ChromatophoreField} field - Read-only field.
   * @param {number} left - Logical horizontal offset.
   * @param {number} top - Logical vertical offset.
   * @param {number} spacing - Logical cell spacing, independent of viewport size.
   */
  drawSkin(field, left, top, spacing) {
    const width = Math.ceil(field.columns / SKIN_SAMPLE_SPAN);
    const height = Math.ceil(field.rows / SKIN_SAMPLE_SPAN);
    if (!this.sampleImage || this.samples.width !== width || this.samples.height !== height) {
      this.samples.width = width;
      this.samples.height = height;
      this.sampleImage = this.sampleContext.createImageData(width, height);
    }
    skinSamples(field, this.sampleImage.data);
    // Sharpen after pigment integration, before interpolation, so no disc grid returns.
    sharpenSkin(this.sampleImage.data, width, height);
    this.sampleContext.putImageData(this.sampleImage, 0, 0);
    this.context.imageSmoothingEnabled = true;
    this.context.imageSmoothingQuality = 'high';
    this.context.drawImage(this.samples, left, top, field.columns * spacing, field.rows * spacing);
  }
}
