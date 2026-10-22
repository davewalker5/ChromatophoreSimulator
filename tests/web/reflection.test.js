/** Angular optics, fixed reference colours and attenuation by overlying pigment. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  ANGLE_PRESETS,
  ReflectionSettings,
  reflectionResponses,
} from '../../explorer/js/reflection.js';
import { ChromatophoreField } from '../../explorer/js/model.js';
import {
  iridophoreBase,
  IRIDOPHORE_COLOUR,
  IRIDOPHORE_PATCHES,
  IRIDOPHORE_STRENGTH,
  SKIN_COLOUR,
  skinSamples,
  roundEven,
} from '../../explorer/js/view.js';

test('zero angles preserve the existing reference palette exactly', () => {
  const responses = reflectionResponses();
  assert.ok(responses.every((response) => response.strength === 1));
  assert.ok(
    responses.every((response) =>
      response.colour.every((value, index) => value === IRIDOPHORE_COLOUR[index]),
    ),
  );
  for (const [x, y] of [
    [0, 0],
    [0.24, 0.3],
    [0.76, 0.36],
    [0.48, 0.78],
    [0.5, 0.5],
    [1, 1],
  ]) {
    const patch = Math.max(
      ...IRIDOPHORE_PATCHES.map(([cx, cy, rx, ry]) =>
        Math.exp(-2 * (((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2)),
      ),
    );
    const previous = SKIN_COLOUR.map((base, channel) =>
      roundEven(base + IRIDOPHORE_STRENGTH * patch * (IRIDOPHORE_COLOUR[channel] - base)),
    );
    assert.deepEqual(iridophoreBase(undefined, x, y), previous);
  }
});

test('angles select reflector orientations and shift the reflected hue towards blue', () => {
  const front = reflectionResponses();
  const tilted = reflectionResponses(new ReflectionSettings(60, 0));
  assert.ok(tilted[1].colour[2] / tilted[1].colour[1] > front[1].colour[2] / front[1].colour[1]);
  assert.ok(tilted[1].strength < front[1].strength);
  const right = reflectionResponses(new ReflectionSettings(30, 0));
  const left = reflectionResponses(new ReflectionSettings(-30, 0));
  assert.ok(right[2].strength > right[0].strength);
  assert.ok(left[0].strength > left[2].strength);
  const invisible = reflectionResponses(new ReflectionSettings(60, -60));
  assert.ok(invisible.every((response) => response.strength === 0));
  assert.deepEqual(iridophoreBase(undefined, 0.24, 0.3, invisible), SKIN_COLOUR);
});

test('responses remain bounded, immutable and continuous throughout supported angles', () => {
  for (const view of ANGLE_PRESETS) {
    for (const light of ANGLE_PRESETS) {
      const responses = reflectionResponses(new ReflectionSettings(view, light));
      assert.ok(Object.isFrozen(responses) && responses.every(Object.isFrozen));
      assert.ok(responses.every((response) => response.strength >= 0 && response.strength <= 1.3));
      assert.ok(
        responses.every((response) => response.colour.every((value) => value >= 0 && value <= 255)),
      );
    }
  }
  const before = reflectionResponses(new ReflectionSettings(30, 0));
  const after = reflectionResponses(new ReflectionSettings(30.001, 0));
  before.forEach((response, index) => {
    assert.ok(Math.abs(response.strength - after[index].strength) < 0.001);
    assert.ok(
      response.colour.every(
        (value, channel) => Math.abs(value - after[index].colour[channel]) < 0.01,
      ),
    );
  });
  assert.ok(Object.isFrozen(new ReflectionSettings()));
});

test('pigment attenuates angular changes and rendering leaves model state untouched', () => {
  const field = new ChromatophoreField();
  const tilted = new ReflectionSettings(45, 0);
  const difference = () => {
    const before = JSON.stringify(field);
    const front = skinSamples(field).pixels;
    const angled = skinSamples(field, undefined, undefined, tilted).pixels;
    assert.equal(JSON.stringify(field), before);
    return front.reduce((sum, value, index) => sum + Math.abs(value - angled[index]), 0);
  };
  const contractedDifference = difference();
  assert.ok(contractedDifference > 0);
  field.setExpansion(1);
  field.update(4);
  const expandedDifference = difference();
  assert.ok(expandedDifference > 0 && expandedDifference < contractedDifference);
});

test('invalid camera and light angles are rejected', () => {
  for (const angle of [-61, 61, NaN, Infinity, true, '30']) {
    assert.throws(() => new ReflectionSettings(angle, 0), RangeError);
    assert.throws(() => new ReflectionSettings(0, angle), RangeError);
  }
  assert.throws(() => iridophoreBase(1, -1, 0), RangeError);
  assert.throws(() => iridophoreBase(1, 0, 0, []), RangeError);
});
