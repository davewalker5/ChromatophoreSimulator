/** Draw diagnostic pigment discs; shared palette and logical units live here. */
import { Pigment } from './model.js';

export const LOGICAL_SIZE = 550;
export const MINIMUM_RADIUS = 0.8;
// Illustrative common cuttlefish colours; black represents dark brown.
export const PIGMENT_COLOURS = Object.freeze({
  [Pigment.YELLOW]: Object.freeze([190, 145, 52]),
  [Pigment.RED]: Object.freeze([155, 74, 46]),
  [Pigment.BROWN]: Object.freeze([85, 56, 40]),
  [Pigment.BLACK]: Object.freeze([43, 34, 29]),
});

/**
 * Draw current disc sizes without changing model state or the prepared background.
 * @param {CanvasRenderingContext2D} context - Destination in logical coordinates.
 * @param {import('./model.js').ChromatophoreField} field - Read-only organ state.
 * @param {number} left - Grid's logical horizontal offset.
 * @param {number} top - Grid's logical vertical offset.
 * @param {number} spacing - Logical display units per cell spacing.
 */
export function drawChromatophores(context, field, left, top, spacing) {
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
