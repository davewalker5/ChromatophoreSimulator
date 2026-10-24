import { ReflectionSettings, reflectionResponses } from '../../explorer/js/reflection.js';
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
import {
  roundEven,
  skinSamples,
  sharpenSkin,
  pigmentReflections,
  SKIN_COLOUR,
} from '../../explorer/js/skin-renderer.js';

test('skin sharpening preserves flat colours and strengthens edges without changing alpha', () => {
  const flat = new Uint8ClampedArray([120, 100, 80, 255]);
  assert.deepEqual(sharpenSkin(flat.slice(), 1, 1), flat);
  const edge = new Uint8ClampedArray([80, 80, 80, 255, 160, 160, 160, 255]);
  const result = sharpenSkin(edge.slice(), 2, 1);
  assert.ok(result[0] < edge[0]);
  assert.ok(result[4] > edge[4]);
  assert.equal(result[3], 255);
  assert.equal(result[7], 255);
  const extreme = new Uint8ClampedArray([0, 0, 0, 255, 255, 255, 255, 255]);
  assert.deepEqual(sharpenSkin(extreme.slice(), 2, 1), extreme);
});

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

test('pigments remain balanced and deterministic on odd-width fields', () => {
  const field = new ChromatophoreField(3, 3);
  const counts = Object.values(Pigment).map(
    (pigment) => field.cells.filter((cell) => cell.pigment === pigment).length,
  );
  assert.ok(Math.max(...counts) - Math.min(...counts) <= 1);
  assert.deepEqual(field.geometry, new ChromatophoreField(3, 3).geometry);
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

test('skin samples preserve irregular state and integrate odd edges', () => {
  const field = new ChromatophoreField(50, 50);
  field.setExpansion(0.5);
  field.update(2);
  const before = JSON.stringify(field);
  const { pixels, width, height } = skinSamples(field, undefined, 0);
  assert.equal(width, 13);
  assert.equal(height, 13);
  assert.ok(new Set(pixels).size > 4, 'Irregular geometry produces natural colour variation');
  for (let offset = 3; offset < pixels.length; offset += 4) assert.equal(pixels[offset], 255);
  assert.equal(JSON.stringify(field), before);
  const odd = skinSamples(new ChromatophoreField(3, 5));
  assert.equal(odd.width, 2);
  assert.equal(odd.height, 1);
  assert.ok(odd.pixels.every(Number.isFinite));
  assert.deepEqual([roundEven(2.5), roundEven(3.5), roundEven(-1.5)], [2, 4, -2]);
  assert.ok(pixels[0] < SKIN_COLOUR[0]);
});

test('expanded pigment attenuates but preserves filtered iridophore reflection', () => {
  const field = new ChromatophoreField(50, 50);
  const reflected = skinSamples(field).pixels;
  const bare = skinSamples(field, undefined, 0).pixels;
  let patches = 0;
  for (let offset = 0; offset < reflected.length; offset += 4) {
    const redDrop = bare[offset] - reflected[offset];
    const blueDrop = bare[offset + 2] - reflected[offset + 2];
    if (redDrop > 10) {
      patches++;
      assert.ok(redDrop > blueDrop, 'Reflection adds a blue-green cast');
    }
    assert.ok(redDrop <= 20, 'Reference sheen stays restrained across the field');
  }
  assert.equal(patches, reflected.length / 4, 'Reflective coverage reaches the entire skin');
  const retractedDifference = Math.max(...bare.map((value, index) => value - reflected[index]));
  field.setExpansion(1);
  field.update(4);
  const expanded = skinSamples(field).pixels;
  const expandedBare = skinSamples(field, undefined, 0).pixels;
  const expandedDifference = Math.max(
    ...expandedBare.map((value, index) => value - expanded[index]),
  );
  assert.ok(expandedDifference > 0, 'Reflection survives beneath expanded pigment');
  assert.ok(expandedDifference < retractedDifference, 'Expanded pigment attenuates reflection');
});

test('static targets, all deterministic signals and delayed state traces match Python', () => {
  const result = spawnSync(process.env.PYTHON ?? 'python3', ['tests/web/reference.py'], {
    encoding: 'utf8',
    env: { ...process.env, PYTHONPATH: 'src' },
    maxBuffer: 20 * 1024 * 1024,
  });
  assert.equal(result.status, 0, result.stderr);
  const reference = JSON.parse(result.stdout);
  for (const layout of reference.layouts) {
    const field = new ChromatophoreField(
      layout.rows,
      layout.columns,
      new ResponseParameters(),
      layout.seed,
    );
    field.responseProfiles.forEach((profile, index) =>
      close(
        [...profile.groupId, profile.expansionScale, profile.contractionScale],
        layout.timing[index],
      ),
    );
    field.geometry.forEach((organ, index) =>
      close([organ.x, organ.y, organ.radiusRatio, organ.pigmentIndex], layout.geometry[index]),
    );
  }
  for (const angular of reference.angular) {
    reflectionResponses(new ReflectionSettings(angular.view, angular.light)).forEach(
      (response, index) => close([...response.colour, response.strength], angular.responses[index]),
    );
  }
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
    const skin = skinSamples(
      field,
      undefined,
      undefined,
      new ReflectionSettings(sample.view_angle, sample.light_angle),
    );
    assert.deepEqual([...skin.pixels], sample.pixels);
  }
  for (const trace of reference.traces) {
    const field = new ChromatophoreField(5, 7, new ResponseParameters(0.5, 0.25, 0.5));
    field.applyPattern(Pattern.SPOTS);
    field.update(0.75);
    field.startDynamic(trace.display);
    field.setNaturalTiming(true);
    for (let step = 0; step < 200; step++) {
      if (step === 30) field.dynamic.speed = 2;
      if (step === 80) field.response = new ResponseParameters(2, 0.5, 2);
      if (step === 110) {
        field.setPigmentLevel(Pigment.YELLOW, 0.25);
        field.setPigmentLevel(Pigment.BROWN, 0.5);
        field.setPigmentLevel(Pigment.BLACK, 0);
      }
      if (step === 120) field.setNaturalTiming(false);
      if (step === 150) field.setNaturalTiming(true);
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

test('pigment filters are bounded, colour selective and validate backing light', () => {
  const dark = pigmentReflections([0, 0, 0]);
  const backing = [1, 1, 1];
  const bright = pigmentReflections(backing);
  assert.deepEqual(backing, [1, 1, 1]);
  const difference = (pigment) =>
    bright[pigment].map((value, channel) => value - dark[pigment][channel]);
  for (const pigment of Object.values(Pigment)) {
    assert.ok(bright[pigment].every((value) => value >= 0 && value <= 1));
    assert.ok(dark[pigment].every((value) => value >= 0 && value <= 1));
  }
  const yellow = difference(Pigment.YELLOW);
  const red = difference(Pigment.RED);
  assert.ok(yellow[0] > yellow[1] && yellow[1] > yellow[2] && yellow[2] > 0);
  assert.ok(red[0] > red[1] && red[1] > red[2] && red[2] > 0);
  assert.ok(yellow[1] > red[1]);
  assert.ok(Math.max(...difference(Pigment.BLACK)) < Math.min(...difference(Pigment.BROWN)));
  for (const invalid of [null, [], [1, 1], [NaN, 0, 0], [Infinity, 0, 0], [-1, 0, 0], [2, 0, 0]]) {
    assert.throws(() => pigmentReflections(invalid), RangeError);
  }
});

test('pigment levels preserve source targets, delays and independent groups', () => {
  const field = new ChromatophoreField(3, 5, new ResponseParameters(1, 1, 0.5));
  const targets = Float64Array.from(field.cells, (_, index) => index / 15);
  field.setTargets(targets);
  const originalTargets = [...targets];
  targets.fill(0);
  field.update(0.2);
  const sizes = field.cells.map((cell) => cell.expansion);
  const redCell = field.cells.find((cell) => cell.pigment === Pigment.RED);
  const redDelay = redCell.delayRemaining;
  for (const level of [0.25, 0.5, 0, 1]) {
    field.setPigmentLevel(Pigment.YELLOW, level);
    assert.deepEqual(
      field.cells.map((cell) => cell.expansion),
      sizes,
    );
    close(
      field.cells.map((cell) => cell.targetExpansion),
      originalTargets.map(
        (target, index) => target * (field.cells[index].pigment === Pigment.YELLOW ? level : 1),
      ),
    );
    assert.equal(redCell.delayRemaining, redDelay);
  }
  field.setPigmentLevel(Pigment.RED, 0.5);
  field.update(0.2);
  const delay = redCell.delayRemaining;
  field.setPigmentLevel(Pigment.RED, 0.5);
  assert.equal(redCell.delayRemaining, delay);
  assert.throws(() => {
    field.pigmentLevels[Pigment.RED] = 0;
  }, TypeError);
  for (const level of [-1, 2, NaN, Infinity]) {
    const before = JSON.stringify(field);
    assert.throws(() => field.setPigmentLevel(Pigment.RED, level), RangeError);
    assert.equal(JSON.stringify(field), before);
  }
  assert.throws(() => field.setPigmentLevel('Unknown', 0.5), RangeError);
  field.applyPattern(Pattern.UNIFORM);
  assert.ok(
    field.cells
      .filter((cell) => cell.pigment === Pigment.RED)
      .every((cell) => cell.targetExpansion === 0.25),
  );
  field.resetPigmentLevels();
  assert.ok(field.cells.every((cell) => cell.targetExpansion === 0.5));
});

test('dynamic pigment changes retain phase and delay, and Hold freezes actual sizes', () => {
  const field = new ChromatophoreField(2, 2, new ResponseParameters(1, 1, 0.5));
  field.startDynamic(DynamicDisplay.FLASH);
  field.update(0.25);
  const phase = field.dynamic.phaseSeconds;
  field.setPigmentLevel(Pigment.YELLOW, 0.25);
  assert.equal(field.dynamic.phaseSeconds, phase);
  assert.ok(field.cells.every((cell) => cell.targetExpansion === 0));
  field.update(0.5);
  assert.equal(field.cells[0].targetExpansion, 0.25);
  assert.equal(field.cells[1].targetExpansion, 1);
  const sizes = field.cells.map((cell) => cell.expansion);
  field.hold();
  field.update(2);
  assert.deepEqual(
    field.cells.map((cell) => cell.expansion),
    sizes,
  );
  field.setPigmentLevel(Pigment.YELLOW, 0.5);
  assert.equal(field.cells[0].targetExpansion, sizes[0] * 0.5);
  assert.equal(field.cells[1].targetExpansion, sizes[1]);
});
