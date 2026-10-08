/**
 * Evolving targets, separate from cell responses and rendering.
 * Display phase advances at the selected speed. Signal delay samples an earlier
 * point in simulation time, reconstructing phase from the speed-change history.
 */
import { Pattern, generateTargets, validateDimensions } from './patterns.js';
import { SeededRandom } from './random.js';

export const DYNAMIC_STEP = 1 / 60;
export const TRAVEL_PERIOD = 16;
export const FLASH_PERIOD = 4;
export const MOTTLE_PERIOD = 6;
export const EXCITATION_HOP_SECONDS = 0.12;
export const EXCITATION_HOLD_SECONDS = 4;
export const EXCITATION_REST_SECONDS = 2;
export const DynamicDisplay = Object.freeze({
  TRAVELLING_WAVE: 'Travelling wave',
  RADIAL_PULSE: 'Radial pulse',
  FLASH: 'Flash',
  MOVING_BANDS: 'Moving bands',
  LOCAL_EXCITATION: 'Local excitation',
  CHANGING_MOTTLE: 'Changing mottle',
});

/**
 * Validate a duration in simulation seconds.
 * @param {number} value - Finite, non-negative duration.
 * @throws {RangeError} If the duration is invalid.
 */
export function validateTime(value) {
  if (!Number.isFinite(value) || value < 0)
    throw new RangeError('Seconds must be finite and non-negative');
}

export class DynamicController {
  /**
   * Prepare coordinates, neighbour arrivals and independent sequence clocks.
   * @param {string} display - A member of DynamicDisplay.
   * @param {number} rows - Positive field height.
   * @param {number} columns - Positive field width.
   * @param {{random: function(): number}} source - Generator for mottle seeds.
   * @throws {RangeError} If the display or dimensions are invalid.
   */
  constructor(display, rows, columns, source = Math) {
    validateDimensions(rows, columns);
    if (!Object.values(DynamicDisplay).includes(display)) throw new RangeError('Unknown display');
    this.display = display;
    this.rows = rows;
    this.columns = columns;
    this.elapsed = 0;
    this.phaseSeconds = 0;
    this.speed = 1;
    this.segments = [{ time: 0, phase: 0, speed: 1 }];
    this.mottleSeed = display === DynamicDisplay.CHANGING_MOTTLE ? source.random() : 0;
    this.mottleIndex = -1;
    this.mottleTargets = null;
    this.targets = new Float64Array(rows * columns);
    this.positions = [];
    const scale = Math.max(rows - 1, columns - 1, 1);
    for (let row = 0; row < rows; row++) {
      for (let column = 0; column < columns; column++) {
        // One ruler for both axes preserves circular geometry on rectangles.
        this.positions.push([
          column / Math.max(columns - 1, 1),
          Math.hypot(row - (rows - 1) / 2, column - (columns - 1) / 2) / scale,
        ]);
      }
    }
    this.arrivals = this.neighbourArrivals();
    this.excitationPeriod =
      Math.max(...this.arrivals) + EXCITATION_HOLD_SECONDS + EXCITATION_REST_SECONDS;
  }

  /**
   * Propagate the earliest signal arrival through four-connected neighbours.
   * @returns {Float64Array} Arrival times in display-phase seconds.
   */
  neighbourArrivals() {
    const arrivals = new Float64Array(this.rows * this.columns).fill(-1);
    const source = Math.floor(this.rows / 2) * this.columns + Math.floor(this.columns / 2);
    arrivals[source] = 0;
    const queue = [source];
    // A queue cursor avoids shifting an array on every visit. Breadth-first order
    // reaches each cell by its shortest path; diagonal hops are not permitted.
    for (let head = 0; head < queue.length; head++) {
      const index = queue[head];
      const row = Math.floor(index / this.columns);
      const column = index % this.columns;
      for (const [y, x] of [
        [row - 1, column],
        [row + 1, column],
        [row, column - 1],
        [row, column + 1],
      ]) {
        if (y < 0 || x < 0 || y >= this.rows || x >= this.columns) continue;
        const next = y * this.columns + x;
        if (arrivals[next] < 0) {
          arrivals[next] = arrivals[index] + EXCITATION_HOP_SECONDS;
          queue.push(next);
        }
      }
    }
    return arrivals;
  }

  /**
   * Advance clocks and sample the delayed signal without delaying cells twice.
   * @param {number} seconds - Finite, non-negative simulation step.
   * @param {number} delay - Signal lag in simulation seconds.
   * @returns {Float64Array|null} Borrowed targets, or null during initial delay.
   * @throws {RangeError} If time, delay or speed is invalid.
   */
  advance(seconds, delay) {
    validateTime(seconds);
    validateTime(delay);
    if (!Number.isFinite(this.speed) || this.speed <= 0)
      throw new RangeError('Speed must be positive');
    if (this.speed !== this.segments.at(-1).speed) {
      this.segments.push({ time: this.elapsed, phase: this.phaseSeconds, speed: this.speed });
    }
    this.elapsed += seconds;
    this.phaseSeconds += seconds * this.speed;
    const signalTime = this.elapsed - delay;
    if (signalTime < 0) return null;

    // Locate the last speed change at or before the historical sample. Using the
    // current speed here would move delayed patterns when their speed is changed.
    let lower = 0;
    let upper = this.segments.length;
    while (lower < upper) {
      const middle = Math.floor((lower + upper) / 2);
      if (this.segments[middle].time <= signalTime) lower = middle + 1;
      else upper = middle;
    }
    const segment = this.segments[lower - 1];
    return this.targetsAt(segment.phase + (signalTime - segment.time) * segment.speed);
  }

  /**
   * Evaluate a waveform at an absolute display phase without moving cells.
   * @param {number} phaseSeconds - Non-negative phase time, not wall-clock time.
   * @returns {Float64Array} Borrowed buffer; copy it if retaining across calls.
   * @throws {RangeError} If phase is negative or non-finite.
   */
  targetsAt(phaseSeconds) {
    validateTime(phaseSeconds);
    if (this.display === DynamicDisplay.CHANGING_MOTTLE) {
      const index = Math.floor(phaseSeconds / MOTTLE_PERIOD);
      if (index !== this.mottleIndex) {
        // Recreating a generator from the interval identifies the same mottle
        // even when increasing delay makes the controller revisit an old interval.
        this.mottleTargets = generateTargets(
          Pattern.RANDOM_MOTTLE,
          this.rows,
          this.columns,
          new SeededRandom(`${this.mottleSeed}:${index}`),
        );
        this.mottleIndex = index;
      }
      return this.mottleTargets;
    }
    const phase = (phaseSeconds / TRAVEL_PERIOD) % 1;
    const localTime = phaseSeconds % this.excitationPeriod;
    for (let index = 0; index < this.targets.length; index++) {
      const [x, radius] = this.positions[index];
      let value;
      if (this.display === DynamicDisplay.FLASH) {
        value = Number(phaseSeconds % FLASH_PERIOD < FLASH_PERIOD / 2);
      } else if (this.display === DynamicDisplay.LOCAL_EXCITATION) {
        const sinceArrival = localTime - this.arrivals[index];
        value = Number(sinceArrival >= 0 && sinceArrival < EXCITATION_HOLD_SECONDS);
      } else if (this.display === DynamicDisplay.MOVING_BANDS) {
        // Two full bands cross the field; one cycle moves them half a field width.
        value = (1 + Math.cos(2 * Math.PI * (2 * x - phase))) / 2;
      } else {
        // Cosine fall-off gives a soft-edged travelling band or expanding ring.
        // Outside the radius of influence, ask cells to contract completely.
        const distance =
          this.display === DynamicDisplay.TRAVELLING_WAVE
            ? Math.abs(x - (-0.25 + 1.5 * phase)) / 0.25
            : Math.abs(radius - phase) / 0.2;
        value = distance < 1 ? (1 + Math.cos(Math.PI * distance)) / 2 : 0;
      }
      this.targets[index] = value;
    }
    return this.targets;
  }
}
