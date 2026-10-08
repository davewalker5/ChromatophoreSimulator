# Chromatophore Simulator — Web Explorer

A standalone HTML, CSS and JavaScript port of the Python simulator. All computation and drawing happen in the browser. There are no runtime libraries, external requests or build steps.

## Preview locally

From the repository root:

```sh
python3 -m http.server 8765 --bind 127.0.0.1
```

The explorer can then be opened at:

http://127.0.0.1:8765/explorer/

Python is a convenient local file server but any static HTTP server will work.

Opening `index.html` through `file://` is unsupported.

## Using the simulator

- **Static patterns:** choose Uniform, Checkerboard, Horizontal Bands, Vertical Bands, Spots, Random Mottle or Radial Gradient. Cells move towards the selected target.
- **Dynamic displays:** choose Travelling Wave, Radial Pulse, Flash, Moving Bands, Local Excitation or Changing Mottle. A new selection starts a fresh sequence at 1× and retains current cell sizes.
- **Cell response:** change expansion and contraction rates independently. At the default 0.25 units/s, full expansion takes four seconds. Response delay adds latency.
- **Display speed:** controls how fast the instructions move, independently of cell response rates. It is available while a dynamic display is selected.
- **Hold current sizes:** stops the display and cell movement. Selecting a display afterwards restarts it; Hold is not a resumable pause.
- **Whole field:** expand, contract or independently randomise all cells.
- **Views:** inspect individual discs or their combined skin appearance. Switching views does not change the model.

### Keyboard Shortcuts

Shortcuts work only while focus is inside the simulator, excluding editable controls.

- Static patterns use U/B/H/V/S/M/G in the order above
- Dynamic displays use W/P/F/N/L/T
- E expands, C contracts and R randomises.
- 1, 2 and 3 cycle expansion rate, contraction rate and delay
- 4 cycles display speed.

This is an illustrative model, not a physiological reconstruction. Skin View estimates pigment coverage and enhances contrast; it does not model physical skin optics.

## Source organisation and comments

| Module           | Responsibility                                                |
| ---------------- | ------------------------------------------------------------- |
| `js/model.js`    | Pigment identity, response parameters, cells and field state  |
| `js/patterns.js` | Static target geometry and bilinear mottle interpolation      |
| `js/dynamics.js` | Dynamic signals, neighbour arrivals and delayed phase history |
| `js/random.js`   | Explicit seeded generator for repeatable mottles              |
| `js/view.js`     | Canvas drawing and analytical skin coverage                   |
| `js/app.js`      | Controls, keyboard handling and animation lifecycle           |

## Development checks

Use Node.js 22 or newer and the project's Python 3.14 environment.

From the repository root, set up the Python dependencies in an activated virtual environment and install the development-only browser tools:

```sh
python -m pip install -e '.[dev]'
npm ci
npm test
npm run format:check
python -m pytest -q
python -m ruff check src tests
python -m ruff format --check src tests
```

`npm test` uses Node's built-in test runner.

### The Parity Checks

The **parity checks** verify that the JavaScript simulator produces the same numerical results as the original Python simulator when given the same inputs.

The tests run the Python simulator to generate reference results, then perform equivalent calculations in JavaScript and compare them:

| Check                | What is compared                                                                                                   |
| -------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Static patterns      | Every cell’s target expansion for the six non-random patterns, across three field sizes                            |
| Dynamic displays     | Targets for the five non-random displays at ten points in their cycles                                             |
| Simulation behaviour | Final cell sizes, targets and display phase after 200 updates involving changes to speed, response rates and delay |
| Skin colours         | Calculated colour samples before enlargement, across three field sizes and three expansion levels                  |

Python is needed only when running these development checks; the hosted explorer still runs entirely in JavaScript.

### Browser Tests

For browser checks, keep the preview server running and install the test browsers once:

```sh
npx playwright install chromium firefox webkit
npm run test:browser
BROWSER=firefox npm run test:browser
BROWSER=webkit npm run test:browser
```

The browser script exercises controls, reduced motion, held-state preservation, keyboard behaviour, skin uniformity, hidden-tab lifecycle, responsive layouts and touch emulation.

It also records 120 frame intervals per view.

It writes screenshots and a JSON report to `/tmp/chromatophore-browser-check` by default.

Optional environment settings:

| Variable             | Purpose                                                                        |
| -------------------- | ------------------------------------------------------------------------------ |
| `BASE_URL`           | Explorer URL, including its hosting subdirectory                               |
| `BROWSER`            | `chromium`, `firefox` or `webkit`                                              |
| `BROWSER_EXECUTABLE` | An installed browser executable instead of the bundled one                     |
| `BROWSER_OUTPUT`     | Screenshot and report directory                                                |
| `PLAYWRIGHT_MODULE`  | Alternate Playwright module location, useful with managed development runtimes |
