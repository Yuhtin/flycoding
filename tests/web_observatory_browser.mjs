// Optional browser integration suite. Set PLAYWRIGHT_MODULE and CHROME_PATH; serve the dashboard at OBSERVATORY_URL.
import test, {after} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({executablePath:process.env.CHROME_PATH, headless:true,
  args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
after(() => browser.close());
const configuredUrl = process.env.OBSERVATORY_URL || 'http://127.0.0.1:8772';
const url = configuredUrl.endsWith('/observatory') ? configuredUrl : `${configuredUrl}/observatory`;
const original = JSON.parse(await readFile(new URL('../src/flycodex/web/demo/snapshot.json', import.meta.url)));
function snapshot(step = 1, signal) {
  const state = structuredClone(original);
  delete state.presentation;
  state.status = 'running'; state.busy = false;
  const attempt = state.attempts['adaptive-1'];
  const turn = attempt.turns[0]; turn.step = step;
  delete turn.feedback; delete turn.evaluation;
  if (signal !== undefined) turn.feedback = {signal, delivered_to_neural:true};
  attempt.turns = [turn]; state.attempts = {'adaptive-1':attempt};
  return state;
}
async function mode(page, expected) {
  await page.waitForFunction(value => document.getElementById('body-mode').textContent === value, expected, {timeout:8000});
}

test('live feedback arriving after idle animates once per turn and never replays saved signals', async () => {
  const context = await browser.newContext({reducedMotion:'reduce'});
  try {
    const page = await context.newPage();
    let state = snapshot(1); state.busy = true;
    let disconnected = false;
    await page.route('**/snapshot.json', route => disconnected ? route.abort() : route.fulfill({json:state}));
    await page.goto(url); await mode(page, 'Working');
    state.busy = false; await mode(page, 'Idle');
    state = snapshot(1, 1); await mode(page, 'Positive feedback');
    assert.equal(await page.locator('#feedback').textContent(), 'Positive');
    await mode(page, 'Idle');
    state.budget.used += 1;
    await page.waitForTimeout(1300); assert.equal(await page.locator('#body-mode').textContent(), 'Idle');
    state = snapshot(2); state.busy = true; await mode(page, 'Working');
    state.busy = false; await mode(page, 'Idle');
    state = snapshot(2, -1); await mode(page, 'Negative feedback');
    assert.equal(await page.locator('#feedback').textContent(), 'Negative');
    disconnected = true;
    await page.waitForFunction(() => document.getElementById('connection').textContent.includes('Disconnected'));
    await mode(page, 'Idle');
    state = snapshot(3, -1);
    disconnected = false;
    await page.waitForFunction(() => document.getElementById('connection').textContent.startsWith('Connected'));
    await mode(page, 'Idle');
    state.status = 'completed';
    await page.reload();
    await page.waitForFunction(() => document.getElementById('feedback').textContent === 'Negative');
    await mode(page, 'Idle');
    await page.locator('#history').selectOption('adaptive-1:3');
    state = snapshot(4, 1); await page.waitForTimeout(1300);
    await page.locator('#history').selectOption('live');
    assert.equal(await page.locator('#body-mode').textContent(), 'Idle');
    await page.locator('#replay-play').click(); await mode(page, 'Replaying work');
    state = snapshot(5, -1); await page.waitForTimeout(1300);
    await page.locator('#history').selectOption('live');
    assert.equal(await page.locator('#body-mode').textContent(), 'Idle');
  } finally { await context.close(); }
});

async function countRenders(context) {
  await context.addInitScript(() => {
    window.renderCount = 0;
    const clear = WebGL2RenderingContext.prototype.clear;
    WebGL2RenderingContext.prototype.clear = function(...args) { window.renderCount++; return clear.apply(this,args); };
  });
}
async function settled(page) {
  await page.waitForSelector('#body-stage canvas[data-ready="true"]');
  await page.waitForSelector('#brain-stage canvas[data-ready="true"]');
  await page.waitForFunction(() => {
    const now = performance.now();
    if (window.lastRenderCount !== window.renderCount) {
      window.lastRenderCount = window.renderCount; window.lastRenderAt = now;
    }
    return window.renderCount > 0 && now - window.lastRenderAt > 700;
  }, null, {polling:100, timeout:12000});
  const count = await page.evaluate(() => window.renderCount);
  assert(count > 0, 'The real WebGL scene must render');
  await page.waitForTimeout(1300);
  assert.equal(await page.evaluate(() => window.renderCount), count, 'Paused camera must stop drawing after damping settles');
  return count;
}

test('integrated reduced-motion panel rests, wakes for orbit/zoom/resize, resumes and disposes', async () => {
  const context = await browser.newContext({reducedMotion:'reduce', viewport:{width:1200,height:900}});
  try {
    await countRenders(context);
    const page = await context.newPage();
    await page.goto(url); await page.waitForSelector('canvas[data-ready="true"]');
    let count = await settled(page);
    const canvas = page.locator('#body-stage canvas');
    const bounds = await canvas.boundingBox();
    await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
    await page.mouse.down(); await page.mouse.move(bounds.x + bounds.width / 2 + 100, bounds.y + bounds.height / 2 + 20, {steps:8}); await page.mouse.up();
    assert(await settled(page) > count, 'Orbit must redraw');
    count = await page.evaluate(() => window.renderCount);
    await canvas.focus(); await page.keyboard.press('+');
    assert(await settled(page) > count, 'Keyboard zoom must redraw');
    count = await page.evaluate(() => window.renderCount);
    await page.mouse.wheel(0, 100);
    assert(await settled(page) > count, 'Wheel zoom must redraw');
    count = await page.evaluate(() => window.renderCount);
    const beforeResize = await page.evaluate(() => window.renderCount);
    await page.setViewportSize({width:1000,height:800});
    await page.waitForFunction(before => window.renderCount > before, beforeResize);
    assert(await settled(page) > count, 'Resize must redraw');
    await page.locator('#replay-play').click();
    await mode(page, 'Replaying work');
    const still = await canvas.screenshot();
    await page.locator('#motion-toggle').click();
    await page.waitForTimeout(600);
    assert(!(await canvas.screenshot()).equals(still), 'Resume must advance articulated poses');
    await page.locator('#motion-toggle').click(); await settled(page);
    await page.evaluate(() => window.dispatchEvent(new Event('pagehide')));
    assert.equal(await canvas.count(),0);
    count = await page.evaluate(() => window.renderCount);
    await page.setViewportSize({width:1100,height:850}); await page.waitForTimeout(300);
    assert.equal(await page.evaluate(() => window.renderCount),count,'Disposed viewer must not wake');
  } finally { await context.close(); }
});
