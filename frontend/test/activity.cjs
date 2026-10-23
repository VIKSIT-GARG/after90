const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const ts = require('typescript')
const { renderToStaticMarkup } = require('react-dom/server')
const React = require('react')
// Exercise the production component and scoring without a second implementation.
const source = fs.readFileSync('src/App.tsx', 'utf8').replace("import './App.css'", '') + '\nexport { MatchActivity, activityPoints, demoSnapshot }'
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText
const context = { exports: {}, require }
vm.runInNewContext(compiled, context)
const { MatchActivity, activityPoints, demoSnapshot } = context.exports
const teams = [{ id: 'home', name: 'Home' }, { id: 'away', name: 'Away' }]
const event = (minute, outcome = null, type = 'goal') => ({ id: `e${minute}`, minute, second: 0, type, outcome, team_id: 'home' })
function render(minute, events = []) {
  return renderToStaticMarkup(React.createElement(MatchActivity, { minute, events, teams, onSeek() {} }))
}
test('rolling window excludes unavailable minutes and future events', () => {
  const html = render(29, [event(19), event(20), event(29), event(30)])
  assert.match(html, /available minutes 20.*29/)
  assert.doesNotMatch(html, /Minutes 15/)
  assert.match(html, /Minutes 20 through 24 inclusive: Home 8 points/)
  assert.match(html, /Minutes 25 through 29 inclusive: Home 8 points/)
})
test('boundary minutes have inclusive coverage and no phantom full-time bucket', () => {
  for (const minute of [0, 5, 29, 90]) {
    const html = render(minute, [event(minute)])
    assert.match(html, /Home 8 points/)
    assert.doesNotMatch(html, /Minutes 90 through 90/)
    assert.match(html, new RegExp(`Replay to ${minute}`))
  }
  assert.match(render(90, [event(90)]), /Minutes 85 through 90 inclusive: Home 8 points/)
})
test('only explicit won tackles and completed passes earn points', () => {
  for (const outcome of [null, 'failed', 'unknown', 'lost']) assert.equal(activityPoints(event(1, outcome, 'tackle')), 0)
  assert.equal(activityPoints(event(1, 'won', 'tackle')), 2)
  assert.equal(activityPoints(event(1, 'completed', 'pass')), 1)
  assert.equal(activityPoints(event(1, null, 'pass')), 0)
})
test('preview follows the API exclusive lower window boundary', () => {
  assert.equal(demoSnapshot(14).recent_events.some(e => e.minute === 4), false)
  assert.equal(demoSnapshot(13).recent_events.some(e => e.minute === 4), true)
})

test('API seek retains selection and focus across delayed responses and resets on source switch', async () => {
  const { JSDOM } = require('jsdom')
  const { createRoot } = require('react-dom/client')
  const dom = new JSDOM('<div id="root"></div>')
  global.window = context.window = dom.window
  global.document = dom.window.document
  global.IS_REACT_ACT_ENVIRONMENT = true
  context.AbortController = AbortController
  const pending = []
  context.fetch = (url, { signal } = {}) => new Promise((resolve, reject) => {
    signal?.addEventListener('abort', () => reject(new Error('aborted')))
    if (url.includes('/recap')) resolve({ ok: true, json: async () => ({ mode: 'fan', text: 'Test recap', final_score: {}, stats: {}, moment_ids: [], source: 'template' }) })
    else pending.push({ url, resolve })
  })
  const root = createRoot(document.querySelector('#root'))
  async function respond(minute) {
    const next = pending.shift()
    assert.ok(next.url.endsWith('?minute=' + minute))
    await React.act(async () => next.resolve({ ok: true, json: async () => ({
      match_id: 'test', fixture_version: 'api-1', synthetic: true, minute, teams,
      score: { home: 0, away: 0 }, stats: { shots: {}, passes: {}, possession_percent: {} }, recent_events: [], insights: [],
    }) }))
  }
  async function click(element) { assert.ok(element); await React.act(async () => element.click()) }
  const button = text => [...document.querySelectorAll('button')].find(b => b.textContent === text)
  try {
    await React.act(async () => root.render(React.createElement(context.exports.default)))
    await respond(0)
    await click(button('Jump to full time'))
    await respond(90)
    await click([...document.querySelectorAll('.activity-bucket')].find(b => b.getAttribute('aria-label').startsWith('Minutes 81 through 84')))
    const seekButton = document.querySelector('.activity-seek')
    seekButton.focus()
    await click(seekButton)
    assert.equal(document.querySelector('.activity-panel').getAttribute('aria-busy'), 'true')
    assert.equal(document.activeElement, seekButton)
    await respond(84)
    assert.equal(document.querySelector('.activity-seek'), seekButton)
    assert.equal(document.activeElement, seekButton)
    assert.match(document.querySelector('.activity-details-top strong').textContent, /80.*84/)
    await click(button('Team API'))
    assert.ok(document.querySelector('.activity-panel'))
    await click(button('Local preview'))
    assert.match(document.querySelector('.activity-legend').textContent, /Northstar/)
    await click(button('Team API'))
    assert.match(document.querySelector('.activity-legend').textContent, /Home/)
  } finally {
    await React.act(async () => root.unmount())
    dom.window.close()
    delete global.window
    delete global.document
  }
})
