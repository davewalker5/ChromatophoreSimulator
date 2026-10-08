/** Behavioural checks of the port, including comparisons to live Python outputs. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import {
  Chromatophore,
  ChromatophoreField,
  ResponseParameters,
  Pigment,
} from '../../explorer/js/model.js';
import { Pattern, generateTargets } from '../../explorer/js/patterns.js';
import { DynamicController, DynamicDisplay } from '../../explorer/js/dynamics.js';
import { SeededRandom } from '../../explorer/js/random.js';
import { roundEven, skinSamples, SKIN_COLOUR } from '../../explorer/js/view.js';

/** Assert floating-point sequences agree within a meaningful model tolerance. */
function close(actual, expected, tolerance = 1e-10) {
  assert.equal(actual.length, expected.length);
  for (let index = 0; index < actual.length; index++) {
    assert.ok(
      Math.abs(actual[index] - expected[index]) <= tolerance,
      `index ${index}: ${actual[index]} != ${expected[index]}`,
    );
  }
}

test('cell consumes partial delay, ignores repeated targets and clamps overshoot', () => {
  const cell = new Chromatophore();
  cell.setTarget(1, 0.04);
  cell.update(0.1, new ResponseParameters(1, 0.5));
  close([cell.expansion], [0.06]);
  cell.setTarget(1, 10);
  cell.update(0.1, new ResponseParameters(1, 0.5));
  close([cell.expansion], [0.16]);
  cell.update(10, new ResponseParameters());
  assert.equal(cell.expansion, 1);
  cell.setTarget(0);
  cell.update(0.5, new ResponseParameters(4, 0.5));
  assert.equal(cell.expansion, 0.75);
});

test('validation is atomic and covers dimensions, targets, durations and rates', () => {
  for (const size of [0, -1, 1.5, NaN, Infinity])
    assert.throws(() => new ChromatophoreField(size, 2));
  for (const value of [-1, NaN, Infinity]) {
    assert.throws(() => new ResponseParameters(1, 1, value));
    assert.throws(() => new Chromatophore().update(value, new ResponseParameters()));
  }
  for (const rate of [0, -1, NaN, Infinity]) assert.throws(() => new ResponseParameters(rate));
  const field = new ChromatophoreField(2, 2);
  field.startDynamic(DynamicDisplay.FLASH);
  const original = field.dynamic;
  assert.throws(() => field.setTargets([0, 1, 0, 2]));
  assert.throws(() => field.setTargets([1]));
  assert.throws(() => field.startDynamic('invalid'));
  assert.equal(field.dynamic, original);
  assert.deepEqual(
    field.cells.map((cell) => cell.targetExpansion),
    [0, 0, 0, 0],
  );
});

test('pigments preserve spatial parity on odd-width fields', () => {
  const field = new ChromatophoreField(2, 3);
  assert.deepEqual(
    field.cells.map((cell) => cell.pigment),
    [Pigment.YELLOW, Pigment.RED, Pigment.YELLOW, Pigment.BROWN, Pigment.BLACK, Pigment.BROWN],
  );
});

test('rate changes apply immediately; delay changes affect future static targets', () => {
  const field = new ChromatophoreField(1, 1, new ResponseParameters(1, 1, 1));
  field.setExpansion(1);
  field.update(0.5);
  field.response = new ResponseParameters(2, 1, 0);
  field.update(0.6);
  close([field.cells[0].expansion], [0.2]);
});

test('Hold stops movement and restarting a display resets speed while preserving sizes', () => {
  const field = new ChromatophoreField(3, 3);
  field.startDynamic(DynamicDisplay.FLASH);
  field.dynamic.speed = 2;
  field.update(0.5);
  field.hold();
  const sizes = field.cells.map((cell) => cell.expansion);
  field.update(10);
  assert.deepEqual(
    field.cells.map((cell) => cell.expansion),
    sizes,
  );
  field.startDynamic(DynamicDisplay.RADIAL_PULSE);
  assert.equal(field.dynamic.speed, 1);
  assert.deepEqual(
    field.cells.map((cell) => cell.expansion),
    sizes,
  );
  field.applyPattern(Pattern.UNIFORM);
  assert.equal(field.dynamic, null);
});

test('dynamic fixed steps are independent of frame partitioning', () => {
  for (const frequency of [30, 60, 120, 144]) {
    const field = new ChromatophoreField(7, 9);
    const reference = new ChromatophoreField(7, 9);
    field.startDynamic(DynamicDisplay.TRAVELLING_WAVE);
    reference.startDynamic(DynamicDisplay.TRAVELLING_WAVE);
    for (let index = 0; index < frequency * 5; index++) field.update(1 / frequency);
    reference.update(5);
    close(
      field.cells.map((cell) => cell.expansion),
      reference.cells.map((cell) => cell.expansion),
    );
  }
});

test('delayed signals follow the speed in effect at the historical time', () => {
  const controller = new DynamicController(DynamicDisplay.MOVING_BANDS, 2, 5);
  assert.equal(controller.advance(0.25, 0.5), null);
  controller.advance(0.75, 0.5);
  controller.speed = 2;
  const targets = [...controller.advance(0.25, 0.5)];
  const reference = new DynamicController(DynamicDisplay.MOVING_BANDS, 2, 5);
  close(targets, reference.targetsAt(0.75));
  close(controller.advance(0.5, 0.5), reference.targetsAt(1.5));
});

test('mottles repeat by seed and interval, including historical revisits', () => {
  const first = generateTargets(Pattern.RANDOM_MOTTLE, 13, 17, new SeededRandom('patch'));
  const second = generateTargets(Pattern.RANDOM_MOTTLE, 13, 17, new SeededRandom('patch'));
  assert.deepEqual(first, second);
  assert.ok(first.every((value) => value >= 0 && value <= 1));
  // At the midpoint between two coarse samples, interpolation is their average.
  close([first[3]], [(first[0] + first[6]) / 2]);
  const controller = new DynamicController(
    DynamicDisplay.CHANGING_MOTTLE,
    13,
    17,
    new SeededRandom(1),
  );
  const initial = [...controller.targetsAt(0)];
  assert.deepEqual([...controller.targetsAt(5.99)], initial);
  assert.notDeepEqual([...controller.targetsAt(6)], initial);
  assert.deepEqual([...controller.targetsAt(0)], initial);
});

test('skin samples preserve state and integrate odd edges without grids', () => {
  const field = new ChromatophoreField(50, 50);
  field.setExpansion(0.5);
  field.update(2);
  const before = JSON.stringify(field);
  const { pixels, width, height } = skinSamples(field);
  assert.equal(width, 25);
  assert.equal(height, 25);
  for (let offset = 0; offset < pixels.length; offset += 4) {
    assert.deepEqual(pixels.slice(offset, offset + 4), pixels.slice(0, 4));
  }
  assert.equal(JSON.stringify(field), before);
  const odd = skinSamples(new ChromatophoreField(3, 5));
  assert.equal(odd.width, 3);
  assert.equal(odd.height, 2);
  assert.ok(odd.pixels.every(Number.isFinite));
  assert.deepEqual([roundEven(2.5), roundEven(3.5), roundEven(-1.5)], [2, 4, -2]);
  assert.ok(pixels[0] < SKIN_COLOUR[0]);
});

test('static targets, all deterministic signals and delayed state traces match Python', () => {
  const result = spawnSync(process.env.PYTHON ?? 'python3', ['tests/web/reference.py'], {
    encoding: 'utf8',
    env: { ...process.env, PYTHONPATH: 'src' },
    maxBuffer: 20 * 1024 * 1024,
  });
  assert.equal(result.status, 0, result.stderr);
  const reference = JSON.parse(result.stdout);
  for (const sample of reference.patterns) {
    close(generateTargets(sample.pattern, sample.rows, sample.columns), sample.targets);
  }
  for (const sample of reference.signals) {
    close(
      new DynamicController(sample.display, sample.rows, sample.columns).targetsAt(sample.phase),
      sample.targets,
    );
  }
  for (const sample of reference.skin) {
    const field = new ChromatophoreField(sample.rows, sample.columns);
    field.setExpansion(sample.expansion);
    field.update(4);
    assert.deepEqual([...skinSamples(field).pixels], sample.pixels);
  }
  for (const trace of reference.traces) {
    const field = new ChromatophoreField(5, 7, new ResponseParameters(0.5, 0.25, 0.5));
    field.applyPattern(Pattern.SPOTS);
    field.update(0.75);
    field.startDynamic(trace.display);
    for (let step = 0; step < 200; step++) {
      if (step === 30) field.dynamic.speed = 2;
      if (step === 80) field.response = new ResponseParameters(2, 0.5, 2);
      if (step === 140) field.dynamic.speed = 0.5;
      field.update([0.01, 0.04, 0.025, 0.1][step % 4]);
    }
    close(
      field.cells.map((cell) => cell.expansion),
      trace.expansion,
    );
    close(
      field.cells.map((cell) => cell.targetExpansion),
      trace.targets,
    );
    close([field.dynamic.phaseSeconds], [trace.phase]);
  }
});
