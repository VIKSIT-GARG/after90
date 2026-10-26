const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const ts = require('typescript')
const React = require('react')
const { renderToStaticMarkup } = require('react-dom/server')

// Test the actual production component and scoring logic.
// After90 now uses backend API data only; Local Preview was removed.
const source =
  fs.readFileSync('src/App.tsx', 'utf8')
    .replace("import './App.css'", '') +
  '\nexport { MatchActivity, activityPoints }'

const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    jsx: ts.JsxEmit.ReactJSX,
  },
}).outputText

const context = {
  exports: {},
  require,
}

vm.runInNewContext(compiled, context)

const {
  MatchActivity,
  activityPoints,
} = context.exports

const teams = [
  { id: 'home', name: 'Home' },
  { id: 'away', name: 'Away' },
]

const event = (minute, outcome = null, type = 'goal') => ({
  id: `e${minute}`,
  minute,
  second: 0,
  type,
  outcome,
  team_id: 'home',
})

function render(minute, events = []) {
  return renderToStaticMarkup(
    React.createElement(MatchActivity, {
      minute,
      events,
      teams,
      onSeek() {},
    })
  )
}

// ------------------------------------------------------------
// TEST 1: Rolling activity window
// ------------------------------------------------------------

test('rolling window excludes unavailable minutes and future events', () => {
  const html = render(29, [
    event(19),
    event(20),
    event(29),
    event(30),
  ])

  assert.match(html, /available minutes 20.*29/)
  assert.doesNotMatch(html, /Minutes 15/)

  assert.match(
    html,
    /Minutes 20 through 24 inclusive: Home 8 points/
  )

  assert.match(
    html,
    /Minutes 25 through 29 inclusive: Home 8 points/
  )
})

// ------------------------------------------------------------
// TEST 2: Boundary minutes
// ------------------------------------------------------------

test('boundary minutes have inclusive coverage and no phantom full-time bucket', () => {
  for (const minute of [0, 5, 29, 90]) {
    const html = render(minute, [event(minute)])

    assert.match(html, /Home 8 points/)
    assert.doesNotMatch(html, /Minutes 90 through 90/)
    assert.match(html, new RegExp(`Replay to ${minute}`))
  }

  assert.match(
    render(90, [event(90)]),
    /Minutes 85 through 90 inclusive: Home 8 points/
  )
})

// ------------------------------------------------------------
// TEST 3: Activity scoring
// ------------------------------------------------------------

test('only explicit won tackles and completed passes earn points', () => {
  for (const outcome of [
    null,
    'failed',
    'unknown',
    'lost',
  ]) {
    assert.equal(
      activityPoints(event(1, outcome, 'tackle')),
      0
    )
  }

  assert.equal(
    activityPoints(event(1, 'won', 'tackle')),
    2
  )

  assert.equal(
    activityPoints(event(1, 'completed', 'pass')),
    1
  )

  assert.equal(
    activityPoints(event(1, null, 'pass')),
    0
  )
})

// ------------------------------------------------------------
// TEST 4: Backend API event window
// Replaces the obsolete demoSnapshot test.
// ------------------------------------------------------------

test('activity respects the available backend API event window', () => {
  const html14 = render(14, [
    event(4),
    event(5),
    event(14),
  ])

  // Minute 14 has an available window from minute 5 to 14.
  assert.match(html14, /available minutes 5.*14/)

  // Minute 4 must not be counted.
  assert.match(
    html14,
    /Minutes 5 through 9 inclusive: Home 8 points/
  )

  assert.match(
    html14,
    /Minutes 10 through 14 inclusive: Home 8 points/
  )

  const html13 = render(13, [
    event(4),
    event(13),
  ])

  // Minute 13 has an available window from minute 4 to 13.
  assert.match(html13, /available minutes 4.*13/)

  assert.match(
    html13,
    /Minutes 4 through 4 inclusive: Home 8 points/
  )

  assert.match(
    html13,
    /Minutes 10 through 13 inclusive: Home 8 points/
  )
})

// ------------------------------------------------------------
// TEST 5: Backend replay and keyboard focus
// Verifies seeking with delayed API responses.
// ------------------------------------------------------------

test('API seek retains selection and focus across delayed responses in backend-only mode', async () => {
  const { JSDOM } = require('jsdom')
  const { createRoot } = require('react-dom/client')

  const dom = new JSDOM('<div id="root"></div>')

  global.window = context.window = dom.window
  global.document = dom.window.document
  global.IS_REACT_ACT_ENVIRONMENT = true

  context.AbortController = AbortController

  const pending = []

  context.fetch = (url, { signal } = {}) =>
    new Promise((resolve, reject) => {
      signal?.addEventListener('abort', () => {
        reject(new Error('aborted'))
      })

      if (url.includes('/recap')) {
        resolve({
          ok: true,
          json: async () => ({
            mode: 'fan',
            text: 'Test recap',
            final_score: {},
            stats: {},
            moment_ids: [],
            source: 'template',
          }),
        })
      } else {
        pending.push({ url, resolve })
      }
    })

  const root = createRoot(
    document.querySelector('#root')
  )

  async function respond(minute) {
    const next = pending.shift()

    assert.ok(
      next,
      `Expected a pending API request for minute ${minute}`
    )

    assert.ok(
      next.url.endsWith('?minute=' + minute),
      `Unexpected API request: ${next.url}`
    )

    await React.act(async () => {
      next.resolve({
        ok: true,
        json: async () => ({
          match_id: 'test',
          fixture_version: 'api-1',
          synthetic: true,
          minute,
          teams,
          score: {
            home: 0,
            away: 0,
          },
          stats: {
            shots: {},
            passes: {},
            possession_percent: {},
          },
          recent_events: [],
          insights: [],
        }),
      })
    })
  }

  async function click(element) {
    assert.ok(
      element,
      'Expected UI element was not found'
    )

    await React.act(async () => {
      element.click()
    })
  }

  const button = text =>
    [...document.querySelectorAll('button')]
      .find(b => b.textContent === text)

  try {
    // Render the actual After90 application.
    await React.act(async () => {
      root.render(
        React.createElement(context.exports.default)
      )
    })

    // Load the first backend snapshot.
    await respond(0)

    assert.ok(
      document.querySelector('.activity-panel')
    )

    // Jump to full time.
    await click(button('Jump to full time'))

    await respond(90)

    // Select the activity interval ending at minute 84.
    const bucket = [
      ...document.querySelectorAll('.activity-bucket'),
    ].find(b =>
      b.getAttribute('aria-label')
        ?.startsWith('Minutes 81 through 84')
    )

    await click(bucket)

    const seekButton =
      document.querySelector('.activity-seek')

    assert.ok(seekButton)

    // Focus the replay button before seeking.
    seekButton.focus()

    assert.equal(
      document.activeElement,
      seekButton
    )

    // Request minute 84.
    await click(seekButton)

    // The existing chart should remain visible while
    // the backend responds.
    assert.equal(
      document.querySelector('.activity-panel')
        .getAttribute('aria-busy'),
      'true'
    )

    // Keyboard focus should remain on the replay button.
    assert.equal(
      document.activeElement,
      seekButton
    )

    // Deliver the delayed backend response.
    await respond(84)

    // React should preserve the selected replay button.
    assert.equal(
      document.querySelector('.activity-seek'),
      seekButton
    )

    assert.equal(
      document.activeElement,
      seekButton
    )

    // Verify that the selected activity interval remains.
    assert.match(
      document.querySelector(
        '.activity-details-top strong'
      ).textContent,
      /80.*84/
    )

    // The activity panel should remain available.
    assert.ok(
      document.querySelector('.activity-panel')
    )

    // Old source-switching controls must not exist.
    assert.equal(
      button('Local preview'),
      undefined
    )

    assert.equal(
      button('Team API'),
      undefined
    )

    // Backend team names should still be displayed.
    const legend =
      document.querySelector('.activity-legend')

    assert.ok(legend)

    assert.match(
      legend.textContent,
      /Home/
    )

    assert.match(
      legend.textContent,
      /Away/
    )

  } finally {
    await React.act(async () => {
      root.unmount()
    })

    dom.window.close()

    delete global.window
    delete global.document
  }
})