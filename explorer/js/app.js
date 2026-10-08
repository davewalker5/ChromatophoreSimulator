/** Page controls and lifecycle; the model itself knows nothing about the DOM. */
import { ChromatophoreField, ResponseParameters } from './model.js';
import { Pattern } from './patterns.js';
import { DynamicDisplay } from './dynamics.js';
import { SeededRandom } from './random.js';
import { FieldView, ViewMode } from './view.js';

export const MAXIMUM_FRAME_SECONDS = 0.1;
const PATTERN_KEYS = ['u', 'b', 'h', 'v', 's', 'm', 'g'];
const DISPLAY_KEYS = ['w', 'p', 'f', 'n', 'l', 't'];

/**
 * Populate a labelled control group while keeping accessible selection state.
 * @param {HTMLElement} container - Parent for the generated buttons.
 * @param {string[]} values - Pattern or display labels.
 * @param {string} kind - Dataset key used by command dispatch.
 * @param {string[]} shortcuts - Matching single-letter keyboard shortcuts.
 */
function addButtons(container, values, kind, shortcuts) {
  values.forEach((value, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = value;
    button.dataset[kind] = value;
    button.setAttribute('aria-pressed', 'false');
    button.setAttribute('aria-keyshortcuts', shortcuts[index]);
    button.title = `${value} (${shortcuts[index].toUpperCase()})`;
    container.append(button);
  });
}

/**
 * Initialise controls, drawing and a visibility-aware animation loop.
 * @throws {Error} If required browser drawing facilities are unavailable.
 */
function initialise() {
  const root = document.querySelector('#simulator');
  const canvas = document.querySelector('#field');
  const field = new ChromatophoreField();
  const view = new FieldView(canvas);
  const source = new SeededRandom(crypto.getRandomValues(new Uint32Array(1))[0]);
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const speed = document.querySelector('#display-speed');
  const expansion = document.querySelector('#expansion-rate');
  const contraction = document.querySelector('#contraction-rate');
  const delay = document.querySelector('#response-delay');
  const activity = document.querySelector('#activity');
  const status = document.querySelector('#status');
  let selectedCommand = null;
  let previousTime = null;
  let frameRequest = null;
  let lastActivity = '';

  addButtons(document.querySelector('#patterns'), Object.values(Pattern), 'pattern', PATTERN_KEYS);
  addButtons(
    document.querySelector('#displays'),
    Object.values(DynamicDisplay),
    'display',
    DISPLAY_KEYS,
  );
  field.applyPattern(Pattern.RANDOM_MOTTLE, source);
  if (reducedMotion.matches) {
    // Start with something meaningful to inspect, but no unsolicited movement.
    for (const cell of field.cells) cell.expansion = cell.targetExpansion;
  }

  /**
   * Refresh selection and descriptions only after user actions, not every frame.
   * @param {string} [announcement] - Optional concise screen-reader message.
   */
  function refreshControls(announcement) {
    document.querySelector('#current-pattern').textContent = field.targetDescription;
    root.querySelectorAll('[data-pattern], [data-display]').forEach((button) => {
      const selected =
        (button.dataset.pattern ?? button.dataset.display) === field.targetDescription;
      button.setAttribute('aria-pressed', String(selected));
    });
    root.querySelectorAll('[data-command]').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.command === selectedCommand));
    });
    root.querySelectorAll('[data-view]').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.view === view.mode));
    });
    speed.disabled = !field.dynamic;
    speed.value = String(field.dynamic?.speed ?? 1);
    const isSkin = view.mode === ViewMode.SKIN;
    canvas.setAttribute(
      'aria-label',
      `${isSkin ? 'Skin' : 'Chromatophore'} View: ${field.targetDescription}, 2,500 pigment organs`,
    );
    document.querySelector('#view-description').textContent = isSkin
      ? 'Pigment coverage is blended into a continuous surface. These are the same cells, seen together.'
      : 'Each coloured disc is one pigment organ. Its radius changes as it follows a target size.';
    if (announcement) status.textContent = announcement;
    view.draw(field);
  }

  /**
   * Translate a clicked button into a model command or a view-only change.
   * @param {MouseEvent} event - Delegated click within the simulator.
   */
  function onClick(event) {
    const button = event.target.closest('button');
    if (!button || button.disabled) return;
    if (button.dataset.view) {
      view.mode = button.dataset.view;
      refreshControls(`${view.mode} View selected.`);
      return;
    }
    selectedCommand = button.dataset.command ?? null;
    if (button.dataset.pattern) field.applyPattern(button.dataset.pattern, source);
    else if (button.dataset.display) field.startDynamic(button.dataset.display, source);
    else if (selectedCommand === 'expand') field.setExpansion(1);
    else if (selectedCommand === 'contract') field.setExpansion(0);
    else if (selectedCommand === 'randomise') field.randomise(source);
    else if (selectedCommand === 'hold') field.hold();
    refreshControls(`${field.targetDescription} selected.`);
  }

  /** Apply validated form values; existing static-delay countdowns are preserved. */
  function onResponseChange() {
    field.response = new ResponseParameters(
      Number(expansion.value),
      Number(contraction.value),
      Number(delay.value),
    );
    status.textContent = `Expansion ${expansion.value} units per second; contraction ${contraction.value} units per second; delay ${delay.value} seconds.`;
  }

  /** Change display speed without changing phase or forgetting its history. */
  function onSpeedChange() {
    if (field.dynamic) field.dynamic.speed = Number(speed.value);
    refreshControls(`Display speed ${speed.value} times.`);
  }

  /**
   * Handle only unmodified shortcuts in this simulator, preserving native keys.
   * @param {KeyboardEvent} event - Keyboard input bubbled from a focused element.
   */
  function onKeyDown(event) {
    if (
      event.ctrlKey ||
      event.metaKey ||
      event.altKey ||
      event.repeat ||
      event.target.isContentEditable ||
      event.target.closest('input, select, textarea')
    )
      return;
    const key = event.key.toLowerCase();
    const patternIndex = PATTERN_KEYS.indexOf(key);
    const displayIndex = DISPLAY_KEYS.indexOf(key);
    let button;
    if (patternIndex >= 0) button = document.querySelectorAll('[data-pattern]')[patternIndex];
    else if (displayIndex >= 0) button = document.querySelectorAll('[data-display]')[displayIndex];
    else if (['e', 'c', 'r'].includes(key)) {
      const command = { e: 'expand', c: 'contract', r: 'randomise' }[key];
      button = document.querySelector(`[data-command="${command}"]`);
    } else if (['1', '2', '3', '4'].includes(key)) {
      const select = [expansion, contraction, delay, speed][Number(key) - 1];
      if (!select.disabled) {
        select.selectedIndex = (select.selectedIndex + 1) % select.options.length;
        select.dispatchEvent(new Event('change'));
      }
    } else return;
    // Space and Tab are deliberately absent: focused buttons activate natively,
    // the page can scroll, and keyboard users retain normal focus navigation.
    event.preventDefault();
    button?.click();
  }

  /**
   * Advance with bounded elapsed time, then draw the same state in either view.
   * @param {number} timestamp - Browser animation timestamp in milliseconds.
   */
  function animate(timestamp) {
    const seconds =
      previousTime === null
        ? 0
        : Math.min((timestamp - previousTime) / 1000, MAXIMUM_FRAME_SECONDS);
    previousTime = timestamp;
    field.update(seconds);
    view.draw(field);
    const moving =
      field.dynamic || field.cells.some((cell) => cell.expansion !== cell.targetExpansion);
    const message = field.dynamic
      ? `Dynamic display · ${field.dynamic.speed}×`
      : moving
        ? 'Moving towards the target'
        : field.targetDescription === 'Held'
          ? 'Held at current sizes'
          : 'Pattern settled';
    if (message !== lastActivity) {
      activity.textContent = message;
      lastActivity = message;
    }
    frameRequest = requestAnimationFrame(animate);
  }

  /** Suspend hidden-tab work and discard wall-clock gaps when the page returns. */
  function onVisibilityChange() {
    if (frameRequest !== null) cancelAnimationFrame(frameRequest);
    previousTime = null;
    frameRequest = document.hidden ? null : requestAnimationFrame(animate);
  }

  /** Stop current motion if a visitor enables reduced motion while using the page. */
  function onMotionPreferenceChange() {
    if (reducedMotion.matches) {
      field.hold();
      selectedCommand = 'hold';
      refreshControls(
        'Movement held because reduced motion is enabled. Select a display to start again.',
      );
    }
  }

  root.addEventListener('click', onClick);
  root.addEventListener('keydown', onKeyDown);
  for (const select of [expansion, contraction, delay])
    select.addEventListener('change', onResponseChange);
  speed.addEventListener('change', onSpeedChange);
  document.addEventListener('visibilitychange', onVisibilityChange);
  reducedMotion.addEventListener('change', onMotionPreferenceChange);
  document.querySelector('#controls').disabled = false;
  root.querySelectorAll('[data-view], #hold').forEach((button) => {
    button.disabled = false;
  });
  refreshControls();
  onVisibilityChange();
}

try {
  initialise();
} catch (error) {
  console.error('Simulator initialisation failed:', error);
  const message = document.querySelector('#startup-error');
  message.hidden = false;
  message.textContent =
    'The simulator could not start. Please try a current browser with JavaScript and Canvas enabled.';
}
