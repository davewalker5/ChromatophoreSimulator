/** Canvas rendering reads state only; drawing never changes targets or time. */
import { Pigment } from './model.js';

export const LOGICAL_SIZE = 550;
export const SKIN_COLOUR = Object.freeze([236, 220, 190]);
export const PIGMENT_COLOURS = Object.freeze({
  [Pigment.YELLOW]: Object.freeze([213, 158, 24]),
  [Pigment.RED]: Object.freeze([190, 48, 43]),
  [Pigment.BROWN]: Object.freeze([104, 49, 31]),
  [Pigment.BLACK]: Object.freeze([30, 27, 26]),
});
export const MINIMUM_RADIUS = 0.8;
export const RADIUS_SPACING_RATIO = 0.45;
export const SKIN_SAMPLE_SPAN = 2;
export const SKIN_CONTRAST = 2;
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
 * Calculate area-weighted skin samples without reducing a raster of circles.
 * @param {import('./model.js').ChromatophoreField} field - State to display.
 * @param {Uint8ClampedArray} [pixels] - Optional reusable RGBA destination.
 * @returns {{width: number, height: number, pixels: Uint8ClampedArray}} Sample image.
 */
export function skinSamples(field, pixels) {
  const width = Math.ceil(field.columns / SKIN_SAMPLE_SPAN);
  const height = Math.ceil(field.rows / SKIN_SAMPLE_SPAN);
  const destination = pixels ?? new Uint8ClampedArray(width * height * 4);
  const spacing = LOGICAL_SIZE / Math.max(field.rows, field.columns);
  const maximumRadius = spacing * RADIUS_SPACING_RATIO;
  const minimumRadius = Math.min(MINIMUM_RADIUS, maximumRadius);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const totals = [0, 0, 0];
      let count = 0;
      for (
        let row = y * SKIN_SAMPLE_SPAN;
        row < Math.min((y + 1) * SKIN_SAMPLE_SPAN, field.rows);
        row++
      ) {
        for (
          let column = x * SKIN_SAMPLE_SPAN;
          column < Math.min((x + 1) * SKIN_SAMPLE_SPAN, field.columns);
          column++
        ) {
          const cell = field.cells[row * field.columns + column];
          const radius = minimumRadius + cell.expansion * (maximumRadius - minimumRadius);
          // The circle covers πr² of its spacing² slot. Analytical coverage avoids
          // false grids caused by raster sampling alternately hitting discs and gaps.
          const coverage = Math.PI * (radius / spacing) ** 2;
          const pigment = PIGMENT_COLOURS[cell.pigment];
          for (let channel = 0; channel < 3; channel++) {
            totals[channel] += SKIN_COLOUR[channel] * (1 - coverage) + pigment[channel] * coverage;
          }
          count++;
        }
      }
      const offset = (y * width + x) * 4;
      for (let channel = 0; channel < 3; channel++) {
        // Round the averaged sample before contrast, just as the Python surface
        // stores integer channels. Count only real cells at odd-sized edges.
        const sample = roundEven(totals[channel] / count);
        destination[offset + channel] = Math.max(
          0,
          Math.min(
            255,
            roundEven(SKIN_COLOUR[channel] + SKIN_CONTRAST * (sample - SKIN_COLOUR[channel])),
          ),
        );
      }
      destination[offset + 3] = 255;
    }
  }
  return { width, height, pixels: destination };
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
    const maximum = spacing * RADIUS_SPACING_RATIO;
    const minimum = Math.min(MINIMUM_RADIUS, maximum);
    // Batch by pigment to avoid thousands of fill calls. Discs do not overlap,
    // so batching preserves the appearance without introducing layer ordering.
    for (const [pigment, colour] of Object.entries(PIGMENT_COLOURS)) {
      context.fillStyle = `rgb(${colour.join(',')})`;
      context.beginPath();
      for (let index = 0; index < field.cells.length; index++) {
        const cell = field.cells[index];
        if (cell.pigment !== pigment) continue;
        const x = left + ((index % field.columns) + 0.5) * spacing;
        const y = top + (Math.floor(index / field.columns) + 0.5) * spacing;
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
    this.sampleContext.putImageData(this.sampleImage, 0, 0);
    this.context.imageSmoothingEnabled = true;
    this.context.imageSmoothingQuality = 'high';
    this.context.drawImage(this.samples, left, top, field.columns * spacing, field.rows * spacing);
  }
}
