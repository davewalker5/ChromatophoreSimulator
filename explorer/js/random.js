/** Repeatable randomness for patches and historical dynamic samples. */
export class SeededRandom {
  /**
   * Hash a seed into a 32-bit state; this is reproducible, not cryptographic.
   * @param {string|number} seed - Stable identifier for a random sequence.
   */
  constructor(seed) {
    this.state = 2166136261;
    for (const character of String(seed)) {
      this.state = Math.imul(this.state ^ character.charCodeAt(0), 16777619) >>> 0;
    }
  }

  /**
   * Advance a Mulberry32 generator, using integer arithmetic across browsers.
   * @returns {number} Uniformly distributed value in [0, 1).
   */
  random() {
    this.state = (this.state + 0x6d2b79f5) >>> 0;
    let value = this.state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  }
}
