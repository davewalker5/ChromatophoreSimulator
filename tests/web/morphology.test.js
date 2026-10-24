/** Physical bounds and analytical integration for irregular organ morphology. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { generateLayout, MAXIMUM_RADIUS_RATIO } from '../../explorer/js/morphology.js';
import { circleRectangleArea } from '../../explorer/js/coverage.js';
import { ChromatophoreField } from '../../explorer/js/model.js';

/** Compare independent floating-point calculations with a numerical tolerance. */
function near(actual, expected, tolerance = 1e-10) {
  assert.ok(Math.abs(actual - expected) < tolerance, `${actual} differs from ${expected}`);
}

test('layout is fixed, variable, bounded and non-overlapping across shapes and seeds', () => {
  for (const [rows, columns] of [
    [1, 1],
    [1, 7],
    [7, 1],
    [3, 5],
    [50, 50],
  ]) {
    const layout = generateLayout(rows, columns);
    assert.deepEqual(layout, generateLayout(rows, columns));
    assert.notDeepEqual(layout, generateLayout(rows, columns, 0));
    assert.ok(Object.isFrozen(layout) && layout.every(Object.isFrozen));
    for (const [index, organ] of layout.entries()) {
      assert.ok(organ.radiusRatio > 0 && organ.radiusRatio <= MAXIMUM_RADIUS_RATIO);
      assert.ok(organ.radiusRatio <= Math.min(organ.x, columns - organ.x, organ.y, rows - organ.y));
      const row = Math.floor(index / columns);
      const column = index % columns;
      for (let nr = Math.max(0, row - 2); nr < Math.min(rows, row + 3); nr++) {
        for (let nc = Math.max(0, column - 2); nc < Math.min(columns, column + 3); nc++) {
          const other = layout[nr * columns + nc];
          if (other === organ) continue;
          assert.ok(
            organ.radiusRatio + other.radiusRatio <
              Math.hypot(organ.x - other.x, organ.y - other.y),
          );
        }
      }
    }
  }
  const layout = generateLayout(50, 50);
  assert.ok(new Set(layout.map((organ) => organ.radiusRatio.toFixed(3))).size > 50);
  const field = new ChromatophoreField();
  const geometry = field.geometry;
  field.randomise({ random: () => 0.42 });
  field.update(1);
  field.setExpansion(1);
  field.hold();
  assert.equal(field.geometry, geometry);
});

test('circle coverage handles containment, tangencies and asymmetric sample crossings', () => {
  const radius = 0.4;
  near(circleRectangleArea(0, 0, radius, [-1, -1, 1, 1]), Math.PI * radius ** 2);
  near(circleRectangleArea(0, 0, radius, [0, 0, 1, 1]), (Math.PI * radius ** 2) / 4);
  near(circleRectangleArea(0, 0, radius, [-0.1, -0.1, 0.1, 0.1]), 0.04);
  assert.equal(circleRectangleArea(0, 0, radius, [radius, 0, 1, 1]), 0);
  assert.equal(circleRectangleArea(0, 0, 0, [-1, -1, 1, 1]), 0);
  const parts = [
    [-1, -1, 0, 0],
    [0, -1, 1, 0],
    [-1, 0, 0, 1],
    [0, 0, 1, 1],
  ];
  near(
    parts.reduce((sum, bounds) => sum + circleRectangleArea(0.13, -0.07, radius, bounds), 0),
    Math.PI * radius ** 2,
  );
  const field = new ChromatophoreField(5, 7);
  for (const span of [1, 2, 4]) {
    let area = 0;
    for (let top = 0; top < field.rows; top += span) {
      for (let left = 0; left < field.columns; left += span) {
        for (const organ of field.geometry) {
          area += circleRectangleArea(organ.x, organ.y, organ.radiusRatio, [
            left,
            top,
            Math.min(left + span, field.columns),
            Math.min(top + span, field.rows),
          ]);
        }
      }
    }
    near(
      area,
      field.geometry.reduce((sum, organ) => sum + Math.PI * organ.radiusRatio ** 2, 0),
    );
  }
});

test('invalid layout and coverage inputs are rejected', () => {
  for (const args of [
    [0, 1],
    [1, -1],
    [1.5, 2],
    [2, 2, -1],
    [2, 2, 2 ** 32],
    [2, 2, true],
  ]) {
    assert.throws(() => generateLayout(...args), RangeError);
  }
  for (const [radius, bounds] of [
    [-1, [0, 0, 1, 1]],
    [NaN, [0, 0, 1, 1]],
    [1, [1, 0, 0, 1]],
    [1, [0, 0, Infinity, 1]],
  ]) {
    assert.throws(() => circleRectangleArea(0, 0, radius, bounds), RangeError);
  }
});

test('skin density calibration restores reference area without tracking current expansion', async () => {
  const { skinCoverageGain, SKIN_REFERENCE_RADIUS_RATIO } = await import(
    '../../explorer/js/skin-renderer.js'
  );
  const field = new ChromatophoreField();
  const gain = skinCoverageGain(field);
  assert.ok(gain > 1);
  const maximumArea = field.geometry.reduce((sum, organ) => sum + organ.radiusRatio ** 2, 0);
  near(gain * maximumArea, field.cells.length * SKIN_REFERENCE_RADIUS_RATIO ** 2);
  field.setExpansion(1);
  field.update(4);
  assert.equal(skinCoverageGain(field), gain);
  field.setExpansion(0);
  field.update(4);
  assert.equal(skinCoverageGain(field), gain);
  field.geometry = field.geometry.map((organ) => ({
    ...organ,
    radiusRatio: SKIN_REFERENCE_RADIUS_RATIO,
  }));
  near(skinCoverageGain(field), 1);
});

test('skin density calibration rejects empty or invalid geometry', async () => {
  const { skinCoverageGain } = await import('../../explorer/js/skin-renderer.js');
  assert.throws(() => skinCoverageGain({ geometry: [] }), RangeError);
  for (const radiusRatio of [0, -1, NaN, Infinity]) {
    assert.throws(() => skinCoverageGain({ geometry: [{ radiusRatio }] }), RangeError);
  }
});
