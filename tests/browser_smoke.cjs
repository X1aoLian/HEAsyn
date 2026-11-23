/* Optional browser smoke test. Requires Playwright and a running workbench. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require('playwright');

(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.BROWSER_EXECUTABLE ? {executablePath: process.env.BROWSER_EXECUTABLE} : {})});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(process.env.WORKBENCH_URL || 'http://127.0.0.1:8765/');
    await page.locator('#rows tr').first().waitFor();
    assert.equal(await page.locator('#rows tr').count(), 80);
    assert.equal(await page.locator('#result-source').textContent(), 'Saved model run');
    const firstTitle = await page.locator('#rows .paper-link').first().textContent();
    const output = path.resolve(__dirname, '../.cache/browser');
    await fs.mkdir(output, {recursive: true});
    await page.screenshot({path: path.join(output, 'desktop.png'), fullPage: true});
    const pixels = await page.locator('#score-chart').evaluate(canvas => {
      const data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
      let visible = 0;
      for (let i = 3; i < data.length; i += 4) if (data[i]) visible++;
      return visible;
    });
    assert(pixels > 500, 'Similarity chart must have nonblank pixels');
    await page.locator('#selected-only').check();
    assert.equal(await page.locator('#rows tr').count(), 20);
    await page.locator('#search').fill('zzzz_no_paper_matches');
    assert(await page.locator('#empty').isVisible());
    await page.locator('#search').fill('');
    await page.locator('#selected-only').uncheck();
    await page.locator('#category').selectOption('out_of_domain');
    assert.equal(await page.locator('#rows tr').count(), 20);
    await page.locator('#category').selectOption('all');
    await page.locator('#rows .paper-link').nth(1).click();
    assert.equal(await page.locator('#detail h3').textContent(), await page.locator('#rows .paper-link').nth(1).textContent());
    const downloadPromise = page.waitForEvent('download');
    await page.locator('#export-csv').click();
    const download = await downloadPromise;
    await download.saveAs(path.join(output, 'ranking.csv'));
    assert((await fs.readFile(path.join(output, 'ranking.csv'), 'utf8')).startsWith('rank,paper_id'));
    await page.locator('[data-preset="broad"]').click();
    await page.locator('#top-k').fill('10');
    await page.locator('#run').click();
    await page.waitForFunction(() => document.querySelector('#result-source').textContent === 'Live model run', null, {timeout: 120000});
    assert.equal(await page.locator('#selected-count').textContent(), '10 / 80');
    assert.notEqual(await page.locator('#rows .paper-link').first().textContent(), firstTitle);
    await page.screenshot({path: path.join(output, 'live-ranking.png'), fullPage: true});
    await page.locator('#cutoff').fill('1');
    await page.locator('#run').click();
    await page.waitForFunction(() => document.querySelector('#selected-count').textContent === '0 / 80');
    await page.locator('#selected-only').check();
    assert(await page.locator('#empty').isVisible());
    await page.reload();
    await page.locator('#rows tr').first().waitFor();
    await page.setViewportSize({width: 390, height: 844});
    await page.screenshot({path: path.join(output, 'mobile.png'), fullPage: true});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No mobile horizontal overflow');
    await page.setViewportSize({width: 320, height: 740});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No narrow-screen horizontal overflow');
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({status: 'passed', dataset: 80, liveInference: true, chartPixels: pixels,
      desktop: '1440x1000', mobile: ['390x844', '320x740'], screenshots: output}));
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
