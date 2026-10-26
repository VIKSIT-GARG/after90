/* Actual browser/replay/accessibility checks. Start the built app/API first. */
const { chromium } = require('playwright')
const AxeBuilder = require('@axe-core/playwright').default
const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const path = require('node:path')
const { pathToFileURL } = require('node:url')

const artifactDir = process.env.AFTER90_ARTIFACTS || '/tmp/after90-browser-evidence'
;(async () => {
  const output = artifactDir
  await fs.mkdir(output, { recursive: true })
  await fs.writeFile(path.join(output, 'report.json'), JSON.stringify({status: 'running'}))
  let launch = { headless: true }
  if (process.env.AFTER90_CHROMIUM_MODULE) {
    const serverless = (await import(pathToFileURL(process.env.AFTER90_CHROMIUM_MODULE).href)).default
    launch = { ...launch, executablePath: process.env.AFTER90_CHROMIUM_EXECUTABLE || await serverless.executablePath(), args: serverless.args }
  } else if (process.env.AFTER90_CHROMIUM_EXECUTABLE) {
    launch.executablePath = process.env.AFTER90_CHROMIUM_EXECUTABLE
  }
  const browser = await chromium.launch(launch)
  let context
  try {
  context = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce',
    ...(process.env.AFTER90_RECORD_VIDEO === '1' ? { recordVideo: { dir: output, size: { width: 1280, height: 900 } } } : {}) })
  const page = await context.newPage()
  const errors = []
  const accessibility = []
  page.on('pageerror', error => errors.push(error.message))
  const pause = () => process.env.AFTER90_RECORD_VIDEO === '1' ? page.waitForTimeout(1800) : Promise.resolve()
  async function seek(minute) {
    await page.locator('#minute-slider').evaluate((element, value) => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(element, String(value))
      element.dispatchEvent(new Event('input', { bubbles: true }))
      element.dispatchEvent(new Event('change', { bubbles: true }))
    }, minute)
    await page.waitForFunction(value => document.querySelector('.clock')?.textContent === (value === 90 ? 'Full time' : String(value).padStart(2, '0') + ':00'), minute)
  }
  async function goal(minute) {
    await seek(minute)
    await page.locator('.insight-select').filter({ hasText: `${minute}'` }).click()
    await page.getByTestId('insight-explanation').waitFor()
    await page.getByTestId('studio-graphic').waitFor()
    await pause()
  }
  async function audit(label) {
    const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()
    accessibility.push({ label, violations: result.violations.map(v => ({ id: v.id, impact: v.impact, description: v.description,
      nodes: v.nodes.map(n => ({ target: n.target, failureSummary: n.failureSummary })) })) })
  }
    await page.goto(process.env.AFTER90_BASE_URL || 'http://127.0.0.1:8000')
    await page.locator('.clock').waitFor()
    await pause()
    await goal(29)
    assert.match(await page.getByTestId('insight-explanation').textContent(), /opened the scoring/i)
    await page.getByRole('button', { name: 'Analyst', exact: true }).click()
    await page.getByTestId('analyst-facts').waitFor()
    assert.match(await page.getByTestId('analyst-facts').textContent(), /Northstar Quay/)
    await page.screenshot({ path: path.join(output, 'desktop.png'), fullPage: true })
    await audit('desktop analyst goal')
    await pause()
    await goal(62)
    assert.match(await page.getByTestId('insight-explanation').textContent(), /equaliz/i)
    await goal(78)
    assert.match(await page.getByTestId('insight-explanation').textContent(), /lead/i)
    await seek(90)
    await page.locator('.recap-text').filter({ hasText: /winning goal/i }).waitFor()
    assert.match(await page.getByTestId('full-time-recap').textContent(), /winning goal/i)
    await page.getByRole('button', { name: 'Fan', exact: true }).click()
    await pause()
    await audit('full time fan')
    if (await page.locator('#team-focus').count()) {
      const scoreBefore = await page.locator('.score').textContent()
      await page.locator('#team-focus').selectOption('red')
      assert.match(await page.locator('.insight-select').first().textContent(), /Copper Vale/)
      assert.equal(await page.locator('.score').textContent(), scoreBefore)
      await audit('optional team focus')
    }
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 })
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `horizontal overflow at ${width}`)
      await page.screenshot({ path: path.join(output, `mobile-${width}.png`), fullPage: true })
      await audit(`mobile ${width}`)
    }
    await page.setViewportSize({ width: 1280, height: 900 })
    // Backend-only replay: source-switching buttons were removed.
    assert.equal(
      await page.getByRole('button', { name: 'Local preview', exact: true }).count(),
      0
    )
    assert.equal(
      await page.getByRole('button', { name: 'Team API', exact: true }).count(),
      0
    )

    // Verify that replay and explanations still work through the API.
    await goal(62)
    await page.getByTestId('generation-notice').first().waitFor()
    await goal(29)
    const seekControl = page.locator('.activity-seek')
    await seekControl.focus()
    await page.keyboard.press('Enter')
    await page.waitForFunction(() => document.querySelector('.activity-panel')?.getAttribute('aria-busy') === 'false')
    assert.equal(await seekControl.evaluate(el => el === document.activeElement), true, 'activity seek lost keyboard focus')
    const violationCount = accessibility.reduce((sum, a) => sum + a.violations.length, 0)
    const report = { status: errors.length || violationCount ? 'failed' : 'passed', browser: browser.version(), assertions: ['goal significance', 'mode facts', 'recap', 'backend-only replay', 'overlay', 'keyboard focus', '320/390px overflow'], runtime_errors: errors, accessibility }
    await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2))
    assert.deepEqual(errors, [])
    assert.equal(violationCount, 0, 'accessibility violations; inspect report.json')
    console.log(JSON.stringify({ status: 'passed', browser: browser.version(), accessibility_states: accessibility.length, runtime_errors: errors.length, output }))
  } finally {
    await context?.close()
    await browser.close()
  }
})().catch(async error => {
  let report = {}
  try { report = JSON.parse(await fs.readFile(path.join(artifactDir, 'report.json'), 'utf8')) } catch {}
  await fs.mkdir(artifactDir, {recursive: true})
  await fs.writeFile(path.join(artifactDir, 'report.json'), JSON.stringify({...report, status: 'failed', error: error.message}, null, 2))
  console.error(error); process.exitCode = 1
})
