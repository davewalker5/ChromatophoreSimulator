/** Coordinate canvas sizing, layout and rendering mode without changing model state. */
import { LOGICAL_SIZE, drawChromatophores } from './chromatophore-renderer.js';
import { SKIN_COLOUR, SkinRenderer } from './skin-renderer.js';
import { ReflectionSettings } from './reflection.js';

export const ViewMode = Object.freeze({ CHROMATOPHORES: 'Chromatophores', SKIN: 'Skin' });

export class FieldView {
  /**
   * Prepare drawing surfaces and a fixed logical coordinate system.
   * @param {HTMLCanvasElement} canvas - Visible drawing surface.
   * @throws {Error} If Canvas 2D is unavailable.
   */
  constructor(canvas) {
    this.canvas = canvas;
    this.context = canvas.getContext('2d', { alpha: false });
    if (!this.context) throw new Error('Canvas 2D is unavailable');
    this.skinRenderer = new SkinRenderer();
    this.mode = ViewMode.CHROMATOPHORES;
    this.reflection = new ReflectionSettings();
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
      this.skinRenderer.draw(context, field, left, top, spacing, this.reflection);
      return;
    }
    drawChromatophores(context, field, left, top, spacing);
  }
}
