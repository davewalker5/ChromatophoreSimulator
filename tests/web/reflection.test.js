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
  IRIDOPHORE_STRENGTH,
  SKIN_COLOUR,
  skinSamples,
  EXPLORER_ANGULAR_CONTRAST,
  roundEven,
} from '../../explorer/js/skin-renderer.js';

test('zero angles give a restrained reference across the entire skin', () => {
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
    const previous = SKIN_COLOUR.map((base, channel) =>
      roundEven(base + IRIDOPHORE_STRENGTH * (IRIDOPHORE_COLOUR[channel] - base)),
    );
    assert.deepEqual(iridophoreBase(undefined, x, y), previous);
  }
});

test('both angle controls produce visible directional contrast', () => {
  assert.ok(reflectionResponses(new ReflectionSettings(60, 0))[24].strength < 0.35);
  assert.ok(reflectionResponses(new ReflectionSettings(0, 60))[24].strength < 0.18);
  const aligned = reflectionResponses(new ReflectionSettings(30, 0));
  assert.ok(aligned[27].strength > 2.5 * aligned[21].strength);
});

test('angled highlights remain visible after backing blending', () => {
  const front = iridophoreBase(undefined, 0.05, 0.5);
  for (const settings of [new ReflectionSettings(-45, 0), new ReflectionSettings(0, -45)]) {
    const responses = reflectionResponses(settings);
    assert.ok(responses[21].strength > 1.8);
    const angled = iridophoreBase(undefined, 0.05, 0.5, responses);
    assert.ok(Math.max(...front.map((value, channel) => Math.abs(value - angled[channel]))) > 12);
  }
});

test('angles select reflector orientations and shift the reflected hue towards blue', () => {
  const front = reflectionResponses();
  const tilted = reflectionResponses(new ReflectionSettings(60, 0));
  assert.ok(tilted[1].colour[2] / tilted[1].colour[1] > front[1].colour[2] / front[1].colour[1]);
  assert.ok(tilted[24].strength < front[24].strength);
  const right = reflectionResponses(new ReflectionSettings(30, 0));
  const left = reflectionResponses(new ReflectionSettings(-30, 0));
  assert.ok(right[27].strength > right[21].strength);
  assert.ok(left[21].strength > left[27].strength);
  const invisible = reflectionResponses(new ReflectionSettings(60, -60));
  assert.ok(invisible.every((response) => response.strength === 0));
  assert.deepEqual(iridophoreBase(undefined, 0.05, 0.5, invisible), SKIN_COLOUR);
});

test('angular sheen covers much of the skin and blends smoothly at region boundaries', () => {
  const before = reflectionResponses(new ReflectionSettings(-45, 0));
  const after = reflectionResponses(new ReflectionSettings(45, 0));
  let changed = 0;
  for (let row = 0; row <= 10; row++) {
    for (let column = 0; column <= 10; column++) {
      const x = column / 10,
        y = row / 10;
      const first = iridophoreBase(undefined, x, y, before);
      const second = iridophoreBase(undefined, x, y, after);
      if (Math.max(...first.map((value, channel) => Math.abs(value - second[channel]))) >= 10)
        changed++;
      const nearby = iridophoreBase(undefined, Math.min(1, x + 0.001), y, after);
      assert.ok(second.every((value, channel) => Math.abs(value - nearby[channel]) <= 1));
    }
  }
  assert.ok(changed >= 80);
});

test('responses remain bounded, immutable and continuous throughout supported angles', () => {
  for (const view of ANGLE_PRESETS) {
    for (const light of ANGLE_PRESETS) {
      const responses = reflectionResponses(new ReflectionSettings(view, light));
      assert.ok(Object.isFrozen(responses) && responses.every(Object.isFrozen));
      assert.ok(responses.every((response) => response.strength >= 0 && response.strength <= 2.9));
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

test('explorer enhancement preserves the reference and strengthens both angle controls', () => {
  const field = new ChromatophoreField();
  const state = JSON.stringify(field);
  const reference = skinSamples(field).pixels;
  const enhanced = (settings) =>
    skinSamples(field, undefined, undefined, settings, EXPLORER_ANGULAR_CONTRAST).pixels;
  assert.deepEqual(enhanced(new ReflectionSettings()), reference);
  const difference = (pixels) =>
    reference.reduce((sum, value, index) => sum + Math.abs(value - pixels[index]), 0);
  for (const settings of [new ReflectionSettings(45, 0), new ReflectionSettings(0, 45)]) {
    const optical = skinSamples(field, undefined, undefined, settings).pixels;
    assert.ok(difference(enhanced(settings)) > 1.3 * difference(optical));
  }
  const settings = new ReflectionSettings(0, 45);
  const contractedDifference = difference(enhanced(settings));
  field.setExpansion(1);
  field.update(4);
  const front = enhanced(new ReflectionSettings());
  const tilted = enhanced(settings);
  const expandedDifference = front.reduce(
    (sum, value, index) => sum + Math.abs(value - tilted[index]),
    0,
  );
  assert.ok(expandedDifference > 0 && expandedDifference < contractedDifference);
  assert.deepEqual(
    enhanced(new ReflectionSettings(60, -60)),
    skinSamples(field, undefined, 0).pixels,
  );
  assert.ok(JSON.stringify(field) !== state); // Only the explicit model update changed state.
  const held = JSON.stringify(field);
  enhanced(settings);
  assert.equal(JSON.stringify(field), held);
});

test('invalid angular enhancement is rejected', () => {
  const field = new ChromatophoreField();
  for (const contrast of [0, -1, NaN, Infinity, true, '2'])
    assert.throws(() => skinSamples(field, undefined, undefined, undefined, contrast), RangeError);
});

test('invalid camera and light angles are rejected', () => {
  for (const angle of [-61, 61, NaN, Infinity, true, '30']) {
    assert.throws(() => new ReflectionSettings(angle, 0), RangeError);
    assert.throws(() => new ReflectionSettings(0, angle), RangeError);
  }
  assert.throws(() => iridophoreBase(1, -1, 0), RangeError);
  assert.throws(() => iridophoreBase(1, 0, 0, []), RangeError);
});
