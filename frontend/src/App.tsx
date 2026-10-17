import './App.css'

const plannedFeatures = [
  {
    title: 'Replay a fictional match',
    description: 'Follow a fixed synthetic fixture at your own pace.',
  },
  {
    title: 'Inspect the evidence',
    description: 'Trace each insight back to verified events and statistics.',
  },
  {
    title: 'Choose your level of detail',
    description: 'Read the same match facts in Fan or Analyst language.',
  },
]

function App() {
  return (
    <div className="site-shell">
      <header className="site-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">M</span>
          <span>MatchLens</span>
        </div>
        <span className="synthetic-label">Synthetic match data</span>
      </header>

      <main>
        <section className="intro" aria-labelledby="page-title">
          <div className="intro-copy">
            <p className="eyebrow">Phase 1 · Frontend foundation</p>
            <h1 id="page-title">A clearer view of a fictional match.</h1>
            <p className="lead">
              MatchLens will turn a replayed synthetic fixture into match facts
              and evidence-backed explanations for fans and analysts.
            </p>
          </div>

          <aside className="status-card" aria-labelledby="status-heading">
            <span className="status-indicator" aria-hidden="true" />
            <p className="card-kicker">Current build</p>
            <h2 id="status-heading">Frontend shell ready</h2>
            <p>
              The synthetic fixture engine and snapshot API are ready. This shell
              does not display match data yet; replay controls and explanations
              arrive in later phases.
            </p>
          </aside>
        </section>

        <section className="features" aria-labelledby="features-heading">
          <div className="section-heading">
            <p className="eyebrow">The planned experience</p>
            <h2 id="features-heading">What comes next</h2>
          </div>
          <ol className="feature-list">
            {plannedFeatures.map((feature, index) => (
              <li key={feature.title}>
                <span className="feature-number" aria-hidden="true">
                  {String(index + 1).padStart(2, '0')}
                </span>
                <div>
                  <h3>{feature.title}</h3>
                  <p>{feature.description}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      </main>

      <footer className="site-footer">
        <span>MatchLens prototype</span>
        <span>Fictional teams, players, and events only</span>
      </footer>
    </div>
  )
}

export default App
