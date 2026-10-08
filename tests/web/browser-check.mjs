/** Browser integration checks. Run against a local server; see explorer/README.md. */
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';

const playwright = await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
const engine = process.env.BROWSER ?? 'chromium';
const browser = await playwright[engine].launch({
  headless: true,
  ...(process.env.BROWSER_EXECUTABLE ? { executablePath: process.env.BROWSER_EXECUTABLE } : {}),
});
const url = process.env.BASE_URL ?? 'http://127.0.0.1:8765/explorer/';
const output = process.env.BROWSER_OUTPUT ?? '/tmp/chromatophore-browser-check';
await mkdir(output, { recursive: true });
const failures = [];
const metrics = [];

/** Capture runtime errors and unexpected network dependencies on a test page. */
function watch(page) {
  page.on('pageerror', (error) => failures.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') failures.push(message.text());
  });
  page.on('response', (response) => {
    if (response.status() >= 400) failures.push(`${response.status()} ${response.url()}`);
  });
  page.on('request', (request) => {
    if (new URL(request.url()).origin !== new URL(url).origin)
      failures.push(`External request: ${request.url()}`);
  });
}

/** Read visible canvas pixels to check that Hold and resize preserve appearance. */
async function canvasImage(page) {
  return page.locator('#field').evaluate((canvas) => canvas.toDataURL());
}

try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1100 },
    reducedMotion: 'reduce',
  });
  watch(page);
  await page.goto(url);
  await page.waitForFunction(() => !document.querySelector('#controls').disabled);
  const initial = await canvasImage(page);
  await page.waitForTimeout(150);
  assert.equal(await canvasImage(page), initial, 'Reduced motion must start settled');
  assert.equal(await page.locator('#display-speed').isDisabled(), true);
  assert.equal(await page.locator('[data-pattern]').count(), 7);
  assert.equal(await page.locator('[data-display]').count(), 6);
  await page.screenshot({ path: `${output}/${engine}-desktop.png`, fullPage: true });

  for (const label of await page.locator('[data-pattern]').allTextContents()) {
    await page.getByRole('button', { name: label, exact: true }).click();
    assert.equal(await page.locator('#current-pattern').textContent(), label);
    assert.equal(
      await page.locator(`[data-pattern="${label}"]`).getAttribute('aria-pressed'),
      'true',
    );
    assert.equal(await page.locator('#display-speed').isDisabled(), true);
  }
  for (const label of await page.locator('[data-display]').allTextContents()) {
    await page.getByRole('button', { name: label, exact: true }).click();
    assert.equal(await page.locator('#current-pattern').textContent(), label);
    assert.equal(await page.locator('#display-speed').inputValue(), '1');
    await page.locator('#display-speed').selectOption('2');
  }
  await page.getByRole('button', { name: 'Hold current sizes' }).click();
  const held = await canvasImage(page);
  await page.waitForTimeout(150);
  assert.equal(await canvasImage(page), held, 'Hold must stop changes');
  await page.getByRole('button', { name: 'Skin View', exact: true }).click();
  assert.notEqual(await canvasImage(page), held, 'Skin should render a different view');
  await page.screenshot({ path: `${output}/${engine}-skin.png`, fullPage: true });
  await page.getByRole('button', { name: 'Chromatophore View', exact: true }).click();
  assert.equal(await canvasImage(page), held, 'Switching view must preserve cell state');

  await page.locator('#field').focus();
  await page.keyboard.press('w');
  assert.equal(await page.locator('#current-pattern').textContent(), 'Travelling wave');
  await page.keyboard.press('4');
  assert.equal(await page.locator('#display-speed').inputValue(), '2');
  await page.locator('#expansion-rate').focus();
  await page.keyboard.press('f');
  assert.equal(
    await page.locator('#current-pattern').textContent(),
    'Travelling wave',
    'No shortcuts in select',
  );
  await page.locator('#field').focus();
  await page.evaluate(() => {
    document.addEventListener(
      'keydown',
      (event) => {
        if (event.key === 'Tab') window.tabWasPrevented = event.defaultPrevented;
      },
      { once: true },
    );
  });
  await page.keyboard.press('Tab');
  assert.equal(await page.evaluate(() => window.tabWasPrevented), false);
  // macOS WebKit may skip buttons with native Tab settings. Test activation
  // with explicit focus rather than overriding the visitor's browser preference.
  await page.locator('#hold').focus();
  await page.keyboard.press('Space');
  assert.equal(await page.locator('#current-pattern').textContent(), 'Held');
  assert.equal(
    await page.locator('#hold').evaluate((button) => getComputedStyle(button).outlineStyle),
    'solid',
  );

  // Uniform pigment coverage should contain no sample-boundary grid in Skin View.
  await page.locator('#expansion-rate').selectOption('4');
  await page.locator('#contraction-rate').selectOption('4');
  await page.getByRole('button', { name: 'Uniform', exact: true }).click();
  await page.waitForFunction(
    () => document.querySelector('#activity').textContent === 'Pattern settled',
  );
  await page.getByRole('button', { name: 'Skin View', exact: true }).click();
  const spread = await page.locator('#field').evaluate((canvas) => {
    const pixels = canvas
      .getContext('2d')
      .getImageData(10, 10, canvas.width - 20, canvas.height - 20).data;
    let difference = 0;
    for (let i = 0; i < pixels.length; i++)
      difference = Math.max(difference, Math.abs(pixels[i] - pixels[i % 4]));
    return difference;
  });
  assert.ok(spread <= 1, `Uniform skin contains a visible grid: channel spread ${spread}`);

  // The real event handler is exercised with a controlled visibility property,
  // since headless browsers do not reproduce physical tab switching consistently.
  await page.getByRole('button', { name: 'Travelling wave', exact: true }).click();
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  const hidden = await canvasImage(page);
  await page.waitForTimeout(200);
  assert.equal(await canvasImage(page), hidden, 'Hidden page should stop drawing');
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await page.waitForTimeout(200);
  assert.notEqual(await canvasImage(page), hidden, 'Visible page should resume');

  for (const mode of ['Chromatophore View', 'Skin View']) {
    await page.getByRole('button', { name: mode, exact: true }).click();
    const timing = await page.evaluate(async () => {
      const samples = [];
      let previous;
      await new Promise((resolve) => {
        /** Collect frame intervals over a sustained animation. */
        function sample(now) {
          if (previous !== undefined) samples.push(now - previous);
          previous = now;
          if (samples.length < 120) requestAnimationFrame(sample);
          else resolve();
        }
        requestAnimationFrame(sample);
      });
      samples.sort((a, b) => a - b);
      return { medianMs: samples[60], p95Ms: samples[114], frames: samples.length };
    });
    metrics.push({ mode, ...timing });
  }

  // Returning to the same viewport restores the identical held image: cell radii
  // and coverage use logical coordinates, not the canvas's current pixel count.
  await page.getByRole('button', { name: 'Hold current sizes' }).click();
  const beforeResize = await canvasImage(page);
  for (const width of [900, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await page.waitForTimeout(75);
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      true,
      `Overflow at ${width}`,
    );
    for (const select of await page.locator('select').all()) {
      const height = await select.evaluate((element) => element.getBoundingClientRect().height);
      assert.ok(height >= 44, `Select must remain a full touch target: ${height}px`);
    }
    const canvas = await page.locator('#field').boundingBox();
    assert.ok(Math.abs(canvas.width - canvas.height) <= 1);
    await page.screenshot({ path: `${output}/${engine}-${width}.png`, fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.waitForTimeout(75);
  assert.equal(await canvasImage(page), beforeResize);
  await page.close();

  const mobileOptions = { ...playwright.devices['iPhone 13'], reducedMotion: 'reduce' };
  // Firefox supports a touch viewport but not Playwright's mobile-layout flag.
  if (engine === 'firefox') delete mobileOptions.isMobile;
  const mobile = await browser.newPage(mobileOptions);
  watch(mobile);
  await mobile.goto(url);
  await mobile.waitForFunction(() => !document.querySelector('#controls').disabled);
  await mobile.getByRole('button', { name: 'Spots', exact: true }).tap();
  assert.equal(await mobile.locator('#current-pattern').textContent(), 'Spots');
  await mobile.getByRole('button', { name: 'Skin View', exact: true }).tap();
  await mobile.getByRole('button', { name: 'Hold current sizes' }).tap();
  assert.equal(
    await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    true,
  );
  await mobile.screenshot({ path: `${output}/${engine}-touch.png`, fullPage: true });
  await mobile.close();
  assert.deepEqual(failures, []);
  const report = {
    engine,
    version: browser.version(),
    url,
    metrics,
    errors: failures,
    mobile: 'iPhone 13 emulation; not physical hardware',
  };
  await writeFile(`${output}/${engine}-report.json`, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
} finally {
  await browser.close();
}
