/** Natural motion, local timing coordination and non-destructive mode changes. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { Chromatophore, ChromatophoreField, ResponseParameters } from '../../explorer/js/model.js';
import { DynamicDisplay } from '../../explorer/js/dynamics.js';
import { generateLayout } from '../../explorer/js/morphology.js';
import { generateResponseProfiles } from '../../explorer/js/timing.js';

/** Check numerical agreement without relying on exact floating-point equality. */
function near(actual, expected) {
  assert.ok(Math.abs(actual - expected) < 1e-12);
}

test('natural response honours delay and reaches 99 percent in the reference time', () => {
  const cell = new Chromatophore();
  const response = new ResponseParameters(4, 4);
  cell.setTarget(1, 0.1);
  cell.update(0.1, response, 1, true);
  assert.equal(cell.expansion, 0);
  cell.update(0.25, response, 1, true);
  near(cell.expansion, 0.99);
  cell.update(0.5, response, 1, true);
  assert.equal(cell.expansion, 1);
  cell.setTarget(0);
  cell.update(0.25, response, 1, true);
  near(cell.expansion, 0.01);
  cell.update(1, response, 1, true);
  assert.equal(cell.expansion, 0);
});

test('natural motion is partition independent and reverses without overshoot', () => {
  const whole = new Chromatophore();
  const split = new Chromatophore();
  const response = new ResponseParameters(2, 4);
  for (const cell of [whole, split]) cell.setTarget(1, 0.04);
  whole.update(0.2, response, 0.9, true);
  for (let index = 0; index < 20; index++) split.update(0.01, response, 0.9, true);
  near(whole.expansion, split.expansion);
  const previous = whole.expansion;
  whole.setTarget(0.1);
  whole.update(0.05, response, 0.9, true);
  assert.ok(whole.expansion > 0.1 && whole.expansion < previous);
  whole.update(10, response, 0.9, true);
  assert.equal(whole.expansion, 0.1);
});

test('local profiles are bounded, reproducible and coordinated without lockstep', () => {
  const geometry = generateLayout(50, 50);
  const profiles = generateResponseProfiles(geometry);
  assert.deepEqual(profiles, generateResponseProfiles(geometry));
  assert.notDeepEqual(profiles, generateResponseProfiles(geometry, 42));
  assert.ok(Object.isFrozen(profiles) && profiles.every(Object.isFrozen));
  const groups = new Map();
  for (const profile of profiles) {
    for (const scale of [profile.expansionScale, profile.contractionScale])
      assert.ok(scale >= 0.85 * 0.97 && scale <= 1.15 * 1.03);
    const key = profile.groupId.join(':');
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(profile);
  }
  assert.ok([...groups.values()].some((group) => group.length > 1));
  for (const group of groups.values()) {
    const scales = group.map((profile) => profile.expansionScale);
    assert.ok(Math.max(...scales) / Math.min(...scales) <= 1.03 / 0.97 + 1e-12);
    const ratios = group.map((profile) => profile.expansionScale / profile.contractionScale);
    near(Math.max(...ratios), Math.min(...ratios));
  }
});

test('mode changes preserve countdowns and dynamic phase, and never resume Hold', () => {
  const field = new ChromatophoreField(3, 5, new ResponseParameters(4, 4, 0.5));
  field.setExpansion(1);
  field.update(0.2);
  const cells = JSON.stringify(field.cells);
  field.setNaturalTiming(true);
  assert.equal(JSON.stringify(field.cells), cells);
  for (const invalid of [0, 1, null, 'natural']) {
    assert.throws(() => field.setNaturalTiming(invalid), RangeError);
    assert.equal(JSON.stringify(field.cells), cells);
    assert.equal(field.naturalTiming, true);
  }
  field.startDynamic(DynamicDisplay.TRAVELLING_WAVE);
  field.update(0.1);
  const controller = field.dynamic;
  const phase = controller.phaseSeconds;
  field.setNaturalTiming(false);
  assert.equal(field.dynamic, controller);
  assert.equal(field.dynamic.phaseSeconds, phase);
  field.hold();
  const sizes = field.cells.map((cell) => cell.expansion);
  field.setNaturalTiming(true);
  field.update(2);
  assert.deepEqual(
    field.cells.map((cell) => cell.expansion),
    sizes,
  );
});

test('natural dynamic substeps honour signal delay without restarting a cell countdown', () => {
  const first = new ChromatophoreField(5, 7, new ResponseParameters(4, 4, 0.5));
  const second = new ChromatophoreField(5, 7, first.response);
  for (const field of [first, second]) {
    field.setNaturalTiming(true);
    field.startDynamic(DynamicDisplay.FLASH);
    field.update(0.25);
    assert.ok(field.cells.every((cell) => cell.expansion === 0));
  }
  first.update(0.5);
  for (let index = 0; index < 50; index++) second.update(0.01);
  first.cells.forEach((cell, index) => near(cell.expansion, second.cells[index].expansion));
  assert.ok(first.cells.every((cell) => cell.expansion > 0.9 && cell.delayRemaining === 0));
});

test('timing profile validation rejects invalid seeds and geometry', () => {
  for (const seed of [-1, 2 ** 32, true])
    assert.throws(() => generateResponseProfiles(generateLayout(2, 2), seed), RangeError);
  for (const geometry of [
    [],
    [{ x: NaN, y: 0, pigmentIndex: 0 }],
    [{ x: 0, y: -1, pigmentIndex: 0 }],
    [{ x: 0, y: 0, pigmentIndex: 4 }],
  ])
    assert.throws(() => generateResponseProfiles(geometry), RangeError);
});

test('invalid kinetics are rejected before consuming a cell delay', () => {
  const cell = new Chromatophore();
  cell.setTarget(1, 0.5);
  const before = JSON.stringify(cell);
  for (const [scale, enabled] of [
    [0, true],
    [-1, true],
    [NaN, true],
    [Infinity, true],
    [1, 1],
  ]) {
    assert.throws(() => cell.update(0.1, new ResponseParameters(), scale, enabled), RangeError);
    assert.equal(JSON.stringify(cell), before);
  }
});
