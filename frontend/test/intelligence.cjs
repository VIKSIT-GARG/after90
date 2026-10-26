const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const ts = require('typescript')
const React = require('react')
const { renderToStaticMarkup } = require('react-dom/server')

function appModule() {
  const source = fs.readFileSync('src/App.tsx', 'utf8').replace("import './App.css'", '').replaceAll("import.meta.env.VITE_ENABLE_TEAM_FOCUS", "undefined") + '\nexport { cacheDuration, GenerationNotice, AnalystFacts, StudioOverlay, prioritizeInsights }'
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText
  const context = { exports: {}, require }
  vm.runInNewContext(compiled, context)
  return context
}
const moduleContext = appModule()
const { cacheDuration, GenerationNotice, AnalystFacts, StudioOverlay, prioritizeInsights } = moduleContext.exports
const teams = [{ id: 'blue', name: 'Northstar Quay' }, { id: 'red', name: 'Copper Vale' }]
const card = { id: 'goal-e072', type: 'goal', minute: 29, team_id: 'blue', evidence_event_ids: ['e071', 'e072'], evidence: { score_before: { blue: 0, red: 0 }, score_after: { blue: 1, red: 0 }, player_id: 'blue_09' } }
const overlay = { insight_id: card.id, match_minute: 29, headline: 'The opening goal', stat_line: 'Northstar Quay 1–0 Copper Vale', display_duration_ms: 8000, priority: 'high', evidence_event_ids: card.evidence_event_ids, source: 'template', synthetic: true }
const evidence = { schema_version: '1.0', match_id: 'test', fixture_version: 'api-1', insight_id: card.id, insight_type: 'goal', minute: 29, as_of_minute: 90, team_id: 'blue', teams: { blue: 'Northstar Quay', red: 'Copper Vale' }, facts: [
  { id: 'score_after', metric: 'score_after', value: { blue: 1, red: 0 } },
  { id: 'possession_blue', metric: 'possession_percent', team_id: 'blue', value: 53, unit: '%', window: { start: 0, end: 90 } },
], evidence_event_ids: card.evidence_event_ids, supported_interpretations: ['GOAL_OPENS_SCORING'], limitations: ['Tactical causes are not established.'] }
function narrative() { return { headline: overlay.headline, selected_fact_ids: ['score_after', 'possession_blue'], interpretation_code: 'GOAL_OPENS_SCORING', fan_explanation: 'Northstar opened the scoring.', analyst_explanation: 'The score changed from 0–0 to 1–0 at minute 29.', limitations: evidence.limitations, evidence } }
function explanation(mode = 'fan', source = 'template') { return { insight_id: card.id, mode, source, text: mode === 'fan' ? 'Fan opening-goal story.' : 'Analyst exact opening-goal facts.', evidence: { ...card.evidence, event_ids: card.evidence_event_ids }, headline: overlay.headline, overlay, narrative: narrative(), limitations: evidence.limitations, metadata: { source, fallback_reason: source === 'template' ? 'not_configured' : null, model_version: 'private-deployment-name', prompt_version: 'prompt-internal', latency_ms: 1 }, cache_expires_in_seconds: 15 } }
function snapshot(minute) { return { match_id: 'test', fixture_version: 'api-1', synthetic: true, minute, teams, score: { blue: minute >= 29 ? 1 : 0, red: 0 }, stats: { shots: {}, passes: {}, possession_percent: { blue: 53, red: 47 } }, recent_events: [], insights: minute >= 29 ? [card] : [] } }
const html = (Component, props) => renderToStaticMarkup(React.createElement(Component, props))

test('templates are never held indefinitely in the client cache', () => {
  assert.equal(cacheDuration(explanation()), 0)
  assert.equal(cacheDuration({ ...explanation('fan', 'foundry'), cache_expires_in_seconds: 600 }), 60000)
  assert.equal(cacheDuration({ ...explanation('fan', 'foundry'), cache_expires_in_seconds: 5 }), 5000)
  assert.equal(cacheDuration({ ...explanation('fan', 'foundry'), cache_expires_in_seconds: NaN }), 0)
})
test('source notice explains controlled Foundry selection without leaking implementation identifiers', () => {
  const foundry = html(GenerationNotice, { value: explanation('fan', 'foundry'), preview: false })
  assert.match(foundry, /AI-selected narrative/)
  assert.match(foundry, /Wording is rendered from verified evidence/)
  assert.doesNotMatch(foundry, /private-deployment-name|prompt-internal/)
  const fallback = html(GenerationNotice, { value: explanation(), preview: false })
  assert.match(fallback, /Evidence-based template/)
  assert.match(fallback, /AI is not connected/)
  assert.match(html(GenerationNotice, { value: explanation(), preview: true }), /Preview template/)
})
test('analyst facts keep team attribution, percentages and inclusive evidence windows', () => {
  const markup = html(AnalystFacts, { narrative: narrative() })
  assert.match(markup, /Northstar Quay 1/)
  assert.match(markup, /Copper Vale 0/)
  assert.match(markup, /53%/)
  assert.match(markup, /Minutes 0.*90, inclusive/)
})
test('studio graphic rejects future or non-synthetic moments and labels actual previews', () => {
  assert.doesNotMatch(html(StudioOverlay, { overlay, minute: 28, preview: false }), /data-testid="studio-graphic"/)
  assert.doesNotMatch(html(StudioOverlay, { overlay: { ...overlay, synthetic: false }, minute: 90, preview: false }), /data-testid="studio-graphic"/)
  const markup = html(StudioOverlay, { overlay, minute: 29, preview: false })
  assert.match(markup, /data-testid="studio-graphic"/)
  assert.match(markup, /Synthetic match data/)
  assert.match(markup, /Suggested display: 8 seconds/)
})

test('mode transitions hide stale content, refresh fallback, ignore aborted replies and reset source', async () => {
  const { JSDOM } = require('jsdom')
  const { createRoot } = require('react-dom/client')
  const context = appModule()
  const dom = new JSDOM('<div id="root"></div>')
  global.window = context.window = dom.window
  global.document = dom.window.document
  global.IS_REACT_ACT_ENVIRONMENT = true
  context.AbortController = AbortController
  const pending = []
  context.fetch = (url, { signal } = {}) => new Promise(resolve => {
    if (url.includes('/insights/')) pending.push({ url, signal, resolve })
    else if (url.includes('/recap')) resolve({ ok: true, json: async () => ({ mode: new URL('http://test' + url).searchParams.get('mode'), source: 'template', text: 'Recap', final_score: { blue: 1, red: 0 }, stats: {}, moment_ids: [card.id] }) })
    else resolve({ ok: true, json: async () => snapshot(Number(new URL('http://test' + url).searchParams.get('minute'))) })
  })
  const root = createRoot(document.querySelector('#root'))
  const button = text => [...document.querySelectorAll('button')].find(b => b.textContent === text)
  const click = async el => { assert.ok(el); await React.act(async () => el.click()) }
  const resolve = async (request, value) => { await React.act(async () => request.resolve({ ok: true, json: async () => value })) }
  try {
    await React.act(async () => root.render(React.createElement(context.exports.default)))
    await click(button('Jump to full time'))
    await click(document.querySelector('.insight-select'))
    const fan = pending.shift()
    assert.match(fan.url, /as_of_minute=90/)
    await resolve(fan, explanation())
    assert.match(document.querySelector('[data-testid="insight-explanation"]').textContent, /Fan opening-goal story/)
    assert.ok(document.querySelector('[data-testid="studio-graphic"]'))
    await click(button('Analyst'))
    assert.doesNotMatch(document.querySelector('[data-testid="insight-explanation"]').textContent, /Fan opening-goal story/)
    const analyst = pending.shift()
    await resolve(analyst, explanation('analyst'))
    assert.ok(document.querySelector('[data-testid="analyst-facts"]'))
    assert.match(document.querySelector('[data-testid="insight-explanation"]').textContent, /Analyst exact/)
    await click(button('Refresh explanation'))
    const retry = pending.shift()
    await click(button('Fan'))
    const freshFan = pending.shift()
    assert.equal(retry.signal.aborted, true)
    await resolve(retry, { ...explanation('analyst'), text: 'STALE ABORTED RESPONSE' })
    assert.doesNotMatch(document.body.textContent, /STALE ABORTED RESPONSE/)
    await resolve(freshFan, explanation())
        // Backend-only mode: the obsolete Local Preview controls must not exist.
    assert.equal(button('Local preview'), undefined)
    assert.equal(button('Team API'), undefined)

    // The latest valid Fan explanation remains visible.
    assert.match(
      document.querySelector('[data-testid="insight-explanation"]').textContent,
      /Fan opening-goal story/
    )

    // Studio graphics continue to use verified API evidence.
    assert.ok(document.querySelector('[data-testid="studio-graphic"]'))
  } finally {
    await React.act(async () => root.unmount())
    dom.window.close()
    delete global.window
    delete global.document
  }
})


test('optional team preference only changes ordering and preserves every factual object', () => {
  const list = [{ ...card, id: 'home-early', team_id: 'blue' }, { ...card, id: 'away-mid', team_id: 'red' }, { ...card, id: 'home-late', team_id: 'blue' }]
  const before = JSON.stringify(list)
  const order = moduleContext.exports.prioritizeInsights(list, 'red')
  assert.deepEqual(Array.from(order, item => item.id), ['away-mid', 'home-late', 'home-early'])
  assert.equal(JSON.stringify(list), before)
  assert.equal(order.find(item => item.id === 'away-mid'), list[1])
  assert.deepEqual(Array.from(moduleContext.exports.prioritizeInsights(list, null), item => item.id), ['home-late', 'away-mid', 'home-early'])
})
