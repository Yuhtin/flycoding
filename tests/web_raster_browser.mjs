// Optional browser regression: PLAYWRIGHT_MODULE, CHROME_PATH, FLYCODING_URL.
// Uses only the bundled recording. It never starts a coding backend.
import assert from 'node:assert/strict';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const url = process.env.FLYCODING_URL || 'http://127.0.0.1:8767';
const results = [];
for (const gpu of ['swiftshader', 'default']) {
  const server = await chromium.launchServer({executablePath: process.env.CHROME_PATH, headless: true,
    args: gpu === 'swiftshader' ? ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] : []});
  try {
    const browser = await chromium.connect(server.wsEndpoint());
    for (const deviceScaleFactor of [1, 2]) {
      const context = await browser.newContext({viewport: {width: 1440, height: 900}, deviceScaleFactor, reducedMotion: 'reduce'});
      try {
        const page = await context.newPage();
        await page.clock.install();
        // Deliberately bright backing tests independence from CSS/compositor layers.
        // This is a stress condition, not a claim to reproduce a specific browser bug.
        await page.route('**/player.css', async route => {
          const response = await route.fetch();
          await route.fulfill({response, body: `${await response.text()}\n#brain-stage {background:rgb(154,240,241)!important;}`});
        });
        await page.goto(url);
        await page.waitForFunction(() => !document.querySelector('#play-toggle').disabled, null, {timeout: 30000});
        const pixels = () => page.locator('#brain-stage').evaluate(canvas => {
          const data = canvas.getContext('2d').getImageData(240, 0, 40, 72).data;
          return {alphaMin: Math.min(...data.filter((_, i) => i % 4 === 3)),
            greenMax: Math.max(...data.filter((_, i) => i % 4 === 1))};
        });
        const dark = async () => {
          const value = await pixels();
          assert.equal(value.alphaMin, 255, 'Unrevealed columns must have an opaque backing');
          assert(value.greenMax < 50, 'Unrevealed columns must stay dark over a cyan CSS backing');
          return value;
        };
        await dark();
        await page.locator('#play-toggle').click();
        await page.clock.runFor(100);
        await page.clock.fastForward(10000);
        await page.locator('#play-toggle').click();
        const waiting = await dark();
        const saved = await page.locator('#brain-stage').evaluate(canvas => canvas.toDataURL());
        await page.clock.fastForward(5000);
        assert.equal(await page.locator('#brain-stage').evaluate(canvas => canvas.toDataURL()), saved);
        await page.locator('#play-toggle').click();
        await page.clock.runFor(100);
        await page.clock.fastForward(50000);
        await page.locator('#play-toggle').click();
        await dark();
        results.push({gpu, deviceScaleFactor, waiting, pauseStable: true, replayClears: true});
      } finally {
        await context.close();
      }
    }
  } finally {
    const child = server.process();
    if (child.exitCode === null && child.signalCode === null) {
      const exited = new Promise(resolve => child.once('exit', resolve));
      child.kill('SIGKILL');
      await exited;
    }
  }
}
console.log(JSON.stringify({newModelCalls: 0, results}));
