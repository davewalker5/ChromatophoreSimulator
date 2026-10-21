/** Rendering-independent cell state. All durations are simulation seconds. */
import { DYNAMIC_STEP, DynamicController, validateTime } from './dynamics.js';
import { generateTargets, validateDimensions } from './patterns.js';

export const Pigment = Object.freeze({
  YELLOW: 'Yellow',
  RED: 'Red',
  BROWN: 'Brown',
  BLACK: 'Black',
});
const PIGMENT_TILE = [
  [Pigment.YELLOW, Pigment.RED],
  [Pigment.BROWN, Pigment.BLACK],
];

/**
 * Check normalised expansion before changing state.
 * @param {number} value - Requested current or target expansion.
 * @throws {RangeError} If value is non-finite or outside [0, 1].
 */
function validateExpansion(value) {
  if (!Number.isFinite(value) || value < 0 || value > 1) {
    throw new RangeError('Expansion must be finite and between 0 and 1');
  }
}

export class ResponseParameters {
  /**
   * Create immutable response settings, replaced when the controls change.
   * @param {number} expansionRate - Positive expansion units per second.
   * @param {number} contractionRate - Positive contraction units per second.
   * @param {number} responseDelay - Non-negative delay in seconds.
   * @throws {RangeError} If any setting is invalid.
   */
  constructor(expansionRate = 0.25, contractionRate = 0.25, responseDelay = 0) {
    for (const rate of [expansionRate, contractionRate]) {
      if (!Number.isFinite(rate) || rate <= 0)
        throw new RangeError('Response rates must be positive');
    }
    validateTime(responseDelay);
    this.expansionRate = expansionRate;
    this.contractionRate = contractionRate;
    this.responseDelay = responseDelay;
    Object.freeze(this);
  }
}

export class Chromatophore {
  /**
   * Create one organ; its field owns position and its pigment remains fixed.
   * @param {number} expansion - Initial visible expansion in [0, 1].
   * @param {number} targetExpansion - Initial requested expansion in [0, 1].
   * @param {string} pigment - A member of Pigment.
   * @throws {RangeError} If expansion or pigment is invalid.
   */
  constructor(expansion = 0, targetExpansion = 0, pigment = Pigment.BROWN) {
    validateExpansion(expansion);
    validateExpansion(targetExpansion);
    if (!Object.values(Pigment).includes(pigment)) throw new RangeError('Unknown pigment');
    this.expansion = expansion;
    this.targetExpansion = targetExpansion;
    this.pigment = pigment;
    this.delayRemaining = 0;
  }

  /**
   * Issue a target; repeating it does not restart an existing delay.
   * @param {number} expansion - Normalised requested size.
   * @param {number} responseDelay - Non-negative waiting time in seconds.
   * @throws {RangeError} If target or delay is invalid.
   */
  setTarget(expansion, responseDelay = 0) {
    validateExpansion(expansion);
    validateTime(responseDelay);
    if (expansion === this.targetExpansion) return;
    this.targetExpansion = expansion;
    this.delayRemaining = expansion !== this.expansion ? responseDelay : 0;
  }

  /**
   * Consume latency, then move towards the target without overshoot.
   * @param {number} elapsedSeconds - Non-negative duration of this update.
   * @param {ResponseParameters} response - Validated rates, read on every update.
   * @throws {RangeError} If elapsed time is invalid.
   */
  update(elapsedSeconds, response) {
    validateTime(elapsedSeconds);
    const waiting = Math.min(elapsedSeconds, this.delayRemaining);
    this.delayRemaining -= waiting;
    // A delay may finish partway through a frame. Only the remaining duration
    // contributes movement; at 0.25 units/s, a full expansion takes four seconds.
    const difference = this.targetExpansion - this.expansion;
    const rate = difference > 0 ? response.expansionRate : response.contractionRate;
    const maximumChange = rate * (elapsedSeconds - waiting);
    if (Math.abs(difference) <= maximumChange) this.expansion = this.targetExpansion;
    else this.expansion += Math.sign(difference) * maximumChange;
  }
}

export class ChromatophoreField {
  /**
   * Create a row-major field with the origin at the upper-left.
   * @param {number} rows - Positive height in cells.
   * @param {number} columns - Positive width in cells.
   * @param {ResponseParameters} response - Shared immutable response settings.
   * @throws {RangeError} If dimensions are invalid.
   */
  constructor(rows = 50, columns = 50, response = new ResponseParameters()) {
    validateDimensions(rows, columns);
    this.rows = rows;
    this.columns = columns;
    this.response = response;
    this.cells = Array.from({ length: rows * columns }, (_, index) => {
      // Row/column parity preserves the tile on odd-width fields as well.
      const pigment = PIGMENT_TILE[Math.floor(index / columns) % 2][(index % columns) % 2];
      return new Chromatophore(0, 0, pigment);
    });
    this.targetDescription = 'Contracted';
    this.dynamic = null;
    this.dynamicRemainder = 0;
    this._pigmentLevels = Object.fromEntries(Object.values(Pigment).map((pigment) => [pigment, 1]));
    this.sourceTargets = new Float64Array(this.cells.length);
  }

  /** Return an immutable snapshot of group target multipliers in [0, 1]. */
  get pigmentLevels() {
    return Object.freeze({ ...this._pigmentLevels });
  }

  /**
   * Scale one group's source targets; current sizes, other groups and phase remain intact.
   * Static changes use the configured delay; dynamics apply levels on the next signal update.
   * Held sizes become the static source. Repeated changes never compound multipliers.
   * @param {string} pigment - Member of Pigment.
   * @param {number} level - Finite target multiplier in [0, 1].
   * @throws {RangeError} If pigment or level is invalid; state is unchanged.
   */
  setPigmentLevel(pigment, level) {
    if (!Object.values(Pigment).includes(pigment)) throw new RangeError('Unknown pigment');
    validateExpansion(level);
    if (level === this._pigmentLevels[pigment]) return;
    this._pigmentLevels[pigment] = level;
    if (!this.dynamic) {
      this.cells.forEach((cell, index) => {
        if (cell.pigment === pigment)
          cell.setTarget(this.sourceTargets[index] * level, this.response.responseDelay);
      });
      if (this.targetDescription === 'Held') this.targetDescription = 'Pigment mix';
    }
  }

  /** Restore group levels to 1 without resetting current sizes or display phase. */
  resetPigmentLevels() {
    for (const pigment of Object.values(Pigment)) this.setPigmentLevel(pigment, 1);
  }

  /**
   * Start a fresh sequence at 1×, preserving the current cell sizes.
   * @param {string} display - A member of DynamicDisplay.
   * @param {{random: function(): number}} source - Optional sequence generator.
   * @throws {RangeError} If the display is invalid; state remains unchanged.
   */
  startDynamic(display, source = Math) {
    const controller = new DynamicController(display, this.rows, this.columns, source);
    this.hold();
    this.dynamic = controller;
    this.targetDescription = display;
  }

  /** Stop target generation and hold each organ at its current visible size. */
  hold() {
    this.dynamic = null;
    this.dynamicRemainder = 0;
    for (const cell of this.cells) cell.setTarget(cell.expansion);
    this.sourceTargets = Float64Array.from(this.cells, (cell) => cell.expansion);
    this.targetDescription = 'Held';
  }

  /**
   * Validate a complete target field before mutating any cells.
   * @param {ArrayLike<number>} targets - One normalised target per cell.
   * @throws {RangeError} If the count or any target is invalid.
   */
  setTargets(targets) {
    if (targets.length !== this.cells.length) throw new RangeError('Target count must match cells');
    for (const target of targets) validateExpansion(target);
    this.dynamic = null;
    this.sourceTargets = Float64Array.from(targets);
    for (let index = 0; index < this.cells.length; index++) {
      const cell = this.cells[index];
      cell.setTarget(
        this.sourceTargets[index] * this._pigmentLevels[cell.pigment],
        this.response.responseDelay,
      );
    }
    this.targetDescription = 'Custom';
  }

  /**
   * Select static targets without changing current expansion.
   * @param {string} pattern - A member of Pattern.
   * @param {{random: function(): number}} source - Generator used by mottle.
   * @throws {RangeError} If the pattern is invalid.
   */
  applyPattern(pattern, source = Math) {
    this.setTargets(generateTargets(pattern, this.rows, this.columns, source));
    this.targetDescription = pattern;
  }

  /**
   * Give every cell the same target, stopping any dynamic sequence.
   * @param {number} expansion - Requested expansion in [0, 1].
   * @throws {RangeError} If expansion is invalid.
   */
  setExpansion(expansion) {
    validateExpansion(expansion);
    this.setTargets(new Float64Array(this.cells.length).fill(expansion));
    this.targetDescription = `Uniform ${Math.round(expansion * 100)}%`;
  }

  /**
   * Request independent random sizes, unlike the spatially blended mottle.
   * @param {{random: function(): number}} source - Caller-owned generator.
   */
  randomise(source = Math) {
    this.setTargets(Float64Array.from(this.cells, () => source.random()));
    this.targetDescription = 'Randomise';
  }

  /**
   * Advance static movement directly or dynamic movement in fixed substeps.
   * @param {number} elapsedSeconds - Non-negative simulation time to advance.
   * @throws {RangeError} If elapsed time is invalid.
   */
  update(elapsedSeconds) {
    validateTime(elapsedSeconds);
    if (this.dynamic) {
      // Preserve fractional time rather than dropping it on high-refresh displays.
      this.dynamicRemainder += elapsedSeconds;
      const steps = Math.floor((this.dynamicRemainder + 1e-12) / DYNAMIC_STEP);
      this.dynamicRemainder = Math.max(0, this.dynamicRemainder - steps * DYNAMIC_STEP);
      for (let step = 0; step < steps; step++) {
        const targets = this.dynamic.advance(DYNAMIC_STEP, this.response.responseDelay);
        for (let index = 0; index < this.cells.length; index++) {
          // Delay already belongs to the signal history. A fresh per-cell delay
          // every frame would prevent cells from ever following a moving target.
          if (targets) {
            const cell = this.cells[index];
            cell.setTarget(targets[index] * this._pigmentLevels[cell.pigment], 0);
          }
          this.cells[index].update(DYNAMIC_STEP, this.response);
        }
      }
    } else {
      for (const cell of this.cells) cell.update(elapsedSeconds, this.response);
    }
  }
}
