import { useEffect, useRef, useState } from 'react'
import './App.css'
import type { ContextPacket, Fact, IntelligenceFields, NarrativeResult, Overlay } from './ai-contracts'

type Mode = 'fan' | 'analyst'
type Pair = Record<string, number>
type Team = { id: string; name: string }
type Event = { id: string; minute: number; second: number; type: string; team_id: string; player_id: string | null; outcome: string | null; related_event_id: string | null }
type Insight = { id: string; type: string; minute: number; team_id: string; evidence_event_ids: string[]; evidence: Record<string, unknown> }
type Stats = { shots: Pair; passes: Pair; possession_percent: Pair }
type Snapshot = { match_id: string; fixture_version: string; synthetic: boolean; minute: number; teams: Team[]; score: Pair; stats: Stats; possession_available?: boolean; recent_events: Event[]; insights: Insight[] }
type Explanation = IntelligenceFields & { insight_id: string; mode: Mode; text: string; evidence: Record<string, unknown>; source: 'foundry' | 'template' }
type Recap = IntelligenceFields & { mode: Mode; text: string; final_score: Pair; stats: Stats; moment_ids: string[]; source: 'foundry' | 'template' }

const base = '/api/matches/demo'
const speeds = [1, 2, 4] as const
// Optional extension: activate only after the core public release gate passes.
const TEAM_FOCUS_ENABLED = import.meta.env.VITE_ENABLE_TEAM_FOCUS === 'true'
function prioritizeInsights(insights: Insight[], teamId: string | null): Insight[] {
  const latest = [...insights].reverse()
  return teamId ? [...latest.filter(item => item.team_id === teamId), ...latest.filter(item => item.team_id !== teamId)] : latest
}
// Preview mode uses clearly labelled fictional data and never pretends to call AI.
const DEMO_TEAMS: Team[] = [{ id: 'northstar', name: 'Northstar Quay' }, { id: 'copper', name: 'Copper Vale' }]
const DEMO_EVENTS: Event[] = [
  { id: 'e01', minute: 4, second: 12, type: 'pass', team_id: 'northstar', player_id: 'N-08', outcome: 'completed', related_event_id: null },
  { id: 'e02', minute: 11, second: 18, type: 'shot', team_id: 'northstar', player_id: 'N-09', outcome: 'saved', related_event_id: null },
  { id: 'e03', minute: 19, second: 8, type: 'shot', team_id: 'copper', player_id: 'C-10', outcome: 'blocked', related_event_id: null },
  { id: 'e04-shot', minute: 29, second: 20, type: 'shot', team_id: 'northstar', player_id: 'N-09', outcome: 'goal', related_event_id: null },
  { id: 'e04', minute: 29, second: 21, type: 'goal', team_id: 'northstar', player_id: 'N-09', outcome: null, related_event_id: 'e04-shot' },
  { id: 'e05', minute: 41, second: 11, type: 'shot', team_id: 'northstar', player_id: 'N-11', outcome: 'saved', related_event_id: null },
  { id: 'e06-shot', minute: 57, second: 42, type: 'shot', team_id: 'copper', player_id: 'C-10', outcome: 'goal', related_event_id: null },
  { id: 'e06', minute: 57, second: 43, type: 'goal', team_id: 'copper', player_id: 'C-10', outcome: null, related_event_id: 'e06-shot' },
  { id: 'e07', minute: 76, second: 6, type: 'shot', team_id: 'northstar', player_id: 'N-09', outcome: 'saved', related_event_id: null },
  { id: 'e08-shot', minute: 84, second: 36, type: 'shot', team_id: 'northstar', player_id: 'N-11', outcome: 'goal', related_event_id: null },
  { id: 'e08', minute: 84, second: 37, type: 'goal', team_id: 'northstar', player_id: 'N-11', outcome: null, related_event_id: 'e08-shot' },
]
function demoSnapshot(minute: number): Snapshot {
  const events = DEMO_EVENTS.filter(event => event.minute <= minute)
  const homeGoals = events.filter(event => event.type === 'goal' && event.team_id === 'northstar').length
  const awayGoals = events.filter(event => event.type === 'goal' && event.team_id === 'copper').length
  const homeShots = events.filter(event => event.type === 'shot' && event.team_id === 'northstar').length
  const awayShots = events.filter(event => event.type === 'shot' && event.team_id === 'copper').length
  const possession = minute < 20 ? 55 : minute < 60 ? 63 : 58
  const insights: Insight[] = events.filter(event => event.type === 'goal').map(event => ({
    id: 'insight-' + event.id, type: 'goal', minute: event.minute, team_id: event.team_id,
    evidence_event_ids: event.related_event_id ? [event.id, event.related_event_id] : [event.id], evidence: {
      score_before: { northstar: events.filter(e => e.type === 'goal' && e.team_id === 'northstar' && e.minute < event.minute).length,
        copper: events.filter(e => e.type === 'goal' && e.team_id === 'copper' && e.minute < event.minute).length },
      score_after: { northstar: events.filter(e => e.type === 'goal' && e.team_id === 'northstar' && e.minute <= event.minute).length,
        copper: events.filter(e => e.type === 'goal' && e.team_id === 'copper' && e.minute <= event.minute).length },
      player_id: event.player_id,
    }
  }))
  return { match_id: 'after90-local-preview', fixture_version: 'local-preview-1', synthetic: true, minute, teams: DEMO_TEAMS, possession_available: false,
    score: { northstar: homeGoals, copper: awayGoals },
    stats: { shots: { northstar: homeShots, copper: awayShots },
      passes: { northstar: Math.floor(minute * 2.8), copper: Math.floor(minute * 2.1) },
      possession_percent: { northstar: possession, copper: 100 - possession } },
    recent_events: events.filter(event => event.minute > minute - 10), insights }
}
function demoExplanation(insight: Insight, mode: Mode): Explanation {
  const before = insight.evidence.score_before as Pair
  const after = insight.evidence.score_after as Pair
  const team = DEMO_TEAMS.find(t => t.id === insight.team_id)?.name ?? insight.team_id
  return { insight_id: insight.id, mode, source: 'template', evidence: insight.evidence, headline: 'A fictional goal',
    overlay: { insight_id: insight.id, match_minute: insight.minute, headline: 'A fictional goal', stat_line: `${team} scored · ${after.northstar}–${after.copper}`, display_duration_ms: 8000, priority: 'high', evidence_event_ids: insight.evidence_event_ids, source: 'template', synthetic: true },
    text: mode === 'fan'
      ? `${team} scored in minute ${insight.minute}, changing the score from ${before.northstar}–${before.copper} to ${after.northstar}–${after.copper}. This is a sample explanation based on fictional events.`
      : `Verified fictional goal at ${insight.minute}': ${team}. Score transition ${before.northstar}–${before.copper} → ${after.northstar}–${after.copper}; evidence event ${insight.evidence_event_ids.join(', ')}. Preview template, not an AI response.` }
}
function demoRecap(mode: Mode): Recap {
  const final = demoSnapshot(90)
  return { mode, final_score: final.score, stats: final.stats, possession_available: false, moment_ids: final.insights.map(i => i.id), source: 'template',
    text: mode === 'fan' ? 'In this fictional match, Northstar Quay won 2–1 against Copper Vale. The deciding goal came in minute 84. This is a preview recap, not AI-generated commentary.'
      : 'Synthetic fixture summary: Northstar Quay 2–1 Copper Vale. Goals at 29, 57 and 84 minutes. Figures are derived from the small local preview dataset, not the team’s full match simulation.' }
}

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal })
  if (!response.ok) throw new Error('Request failed (' + response.status + ')')
  return response.json() as Promise<T>
}
function isSnapshot(value: Snapshot): boolean {
  return value.synthetic === true && Array.isArray(value.teams) && value.teams.length === 2 &&
    Array.isArray(value.recent_events) && Array.isArray(value.insights) &&
    typeof value.score === 'object' && typeof value.stats === 'object'
}
function title(insight: Insight) {
  return insight.type === 'goal' ? 'Goal confirmed' : insight.type === 'shot_surge' ? 'Shot surge' : 'Possession swing'
}
function source(sourceValue: string) {
  return sourceValue === 'foundry' ? 'AI-selected narrative' : 'Evidence-based template'
}
function eventTitle(event: Event) {
  if (event.type === 'possession_change') return 'Possession changed'
  if (event.type === 'goal') return 'Goal'
  return event.type.charAt(0).toUpperCase() + event.type.slice(1) + (event.outcome ? ' ' + event.outcome : '')
}
function windowText(value: unknown) {
  return Array.isArray(value) && value.length === 2 ? value[0] + '–' + value[1] : '—'
}

// An explainable activity index, not xG, possession percentage, or an AI prediction.
// Only events supplied by the active data source are scored.
function activityPoints(event: Event): number {
  if (event.type === 'goal') return 8
  if (event.type === 'shot') return 4
  if (event.type === 'possession_change') return 2
  if (event.type === 'tackle') return event.outcome === 'won' ? 2 : 0
  if (event.type === 'pass') return event.outcome === 'completed' ? 1 : 0
  return 0
}

type ActivityBucket = { start: number; availableStart: number; end: number; events: Event[]; scores: Pair }

function MatchActivity({ events, teams, minute, onSeek, loading = false }: {
  events: Event[]; teams: Team[]; minute: number; onSeek: (minute: number) => void; loading?: boolean
}) {
  const [selectedStart, setSelectedStart] = useState<number | null>(null)
  // Snapshots expose a rolling recent-events window, not a complete match feed.
  // Clip labels to supplied integer minutes; the final bucket also includes minute 90.
  // No unseen minutes are estimated.
  const windowStart = Math.max(0, minute - 9)
  const visible = events.filter(event => event.minute >= windowStart && event.minute <= minute)
  const firstBucket = Math.min(85, Math.floor(windowStart / 5) * 5)
  const lastBucket = Math.min(85, Math.floor(minute / 5) * 5)
  const buckets: ActivityBucket[] = []
  for (let start = firstBucket; start <= lastBucket; start += 5) {
    const bucketEvents = visible.filter(event => event.minute >= start && (event.minute < start + 5 || start === 85 && event.minute === 90))
    const scores: Pair = Object.fromEntries(teams.map(team => [team.id, bucketEvents
      .filter(event => event.team_id === team.id)
      .reduce((sum, event) => sum + activityPoints(event), 0)]))
    buckets.push({ start, availableStart: Math.max(start, windowStart), end: Math.min(minute, start + 4 + (start === 85 ? 1 : 0)), events: bucketEvents, scores })
  }
  const selected = buckets.find(bucket => bucket.start === selectedStart) ?? buckets[buckets.length - 1]
  const maxScore = Math.max(1, ...buckets.flatMap(bucket => teams.map(team => bucket.scores[team.id] ?? 0)))
  return <section className="activity-panel" aria-labelledby="activity-title" aria-busy={loading}>
    <div className="section-head activity-head">
      <div><h2 id="activity-title">Match activity <span className="section-spark">✦</span></h2>
        <p>Event-weighted attacking activity · available minutes {windowStart}'–{minute}' (inclusive)</p></div>
      <span className="activity-pill" role="status">{loading ? 'Loading replay · showing minute ' + minute : 'Transparent metric · not AI'}</span>
    </div>
    <div className="activity-legend" aria-label="Teams">
      {teams.map((team, index) => <span key={team.id}><i className={'activity-key activity-key-' + index} />{team.name}</span>)}
    </div>
    <div className="activity-chart" role="group" aria-label="Select a five-minute match interval">
      {buckets.map(bucket => <button type="button" key={bucket.start}
        className={'activity-bucket' + (selected?.start === bucket.start ? ' is-selected' : '')}
        aria-pressed={selected?.start === bucket.start}
        aria-label={`Minutes ${bucket.availableStart} through ${bucket.end} inclusive: ${teams.map(team => `${team.name} ${bucket.scores[team.id] ?? 0} points`).join(', ')}`}
        onClick={() => setSelectedStart(bucket.start)}>
        <span className="activity-bars">
          {teams.map((team, index) => <span key={team.id} className={'activity-bar activity-bar-' + index}
            style={{ height: `${Math.max(3, (bucket.scores[team.id] ?? 0) / maxScore * 100)}%` }}
            title={`${team.name}: ${bucket.scores[team.id] ?? 0} activity points`} />)}
        </span>
        <span className="activity-tick">{bucket.availableStart}'</span>
      </button>)}
    </div>
    {selected && <div className="activity-details">
      <div className="activity-details-top"><div><strong>{selected.availableStart}'–{selected.end}' inclusive interval</strong>
        <p>{selected.events.length} recorded events in the available window</p></div>
        <button type="button" className="activity-seek" aria-disabled={loading} onClick={() => { if (!loading) onSeek(selected.end) }}>Replay to {selected.end}' ↗</button>
      </div>
      <div className="activity-score-row">{teams.map((team, index) => <span key={team.id}>
        <i className={'activity-key activity-key-' + index} />{team.name} <strong>{selected.scores[team.id] ?? 0} pts</strong>
      </span>)}</div>
      {selected.events.length ? <ul className="activity-events" tabIndex={0} aria-label="Recorded events in the selected activity interval">{selected.events.map(event => <li key={event.id}>
        <span>{event.minute}'{String(event.second).padStart(2, '0')}″</span>
        <strong>{eventTitle(event)}</strong>
        <span>{teams.find(team => team.id === event.team_id)?.name ?? event.team_id}</span>
        <small>+{activityPoints(event)} pts · {event.id}</small>
      </li>)}</ul> : <p className="activity-empty">No supplied events in this interval.</p>}
    </div>}
    <p className="activity-method">How it's scored: completed pass +1 · shot +4 · goal +8 · possession change +2 · successful tackle +2. Failed or unknown passes and tackles +0. Goals are counted as their own event, not as an additional shot. This is a custom event-activity index, not a measure of true momentum or team dominance. Only available minutes are shown; edge intervals may be partial. The final interval includes minute 90.</p>
  </section>
}

function Evidence({ insight, teams }: { insight: Insight; teams: Team[] }) {
  const evidence = insight.evidence
  const focus = teams.find(team => team.id === insight.team_id)
  const other = teams.find(team => team.id !== insight.team_id)
  const facts: string[] = []
  if (insight.type === 'goal') {
    const before = evidence.score_before as Pair | undefined
    const after = evidence.score_after as Pair | undefined
    if (before && after && focus && other) facts.push('Score: ' + before[focus.id] + '–' + before[other.id] + ' → ' + after[focus.id] + '–' + after[other.id])
    if (typeof evidence.player_id === 'string') facts.push('Scorer ID: ' + evidence.player_id)
  } else if (insight.type === 'shot_surge') {
    const counts = evidence.shot_counts as Pair | undefined
    facts.push('Minutes ' + evidence.window_start_minute_inclusive + '–' + evidence.window_end_minute_inclusive)
    if (counts && focus && other) facts.push('Shots: ' + focus.name + ' ' + counts[focus.id] + ', ' + other.name + ' ' + counts[other.id])
  } else {
    const previous = evidence.previous_possession_percent as Pair | undefined
    const current = evidence.current_possession_percent as Pair | undefined
    facts.push('Minutes ' + windowText(evidence.previous_window) + ' → ' + windowText(evidence.current_window))
    if (previous && current && focus) facts.push(focus.name + ' possession: ' + previous[focus.id] + '% → ' + current[focus.id] + '%')
    if (typeof evidence.change_points === 'number') facts.push('Change: ' + evidence.change_points + ' percentage points')
  }
  return <div className="evidence" aria-label="Verified evidence">
    <strong>Verified evidence</strong>
    <ul>{facts.map(fact => <li key={fact}>{fact}</li>)}</ul>
    <p>Event IDs: {insight.evidence_event_ids.join(', ') || 'None supplied'}</p>
  </div>
}


type LoadState<T> = { key: string; value: T | null; error: string | null }
type CacheEntry<T> = { value: T; expires: number }
function cacheDuration(value: IntelligenceFields & { source: string }): number {
  // Transient fallbacks are retried on re-selection/mode change, never pinned by the browser.
  if (value.source !== 'foundry') return 0
  const seconds = value.cache_expires_in_seconds ?? 60
  return Number.isFinite(seconds) ? Math.max(0, Math.min(seconds, 60)) * 1000 : 0
}
function fallbackMessage(reason?: string | null): string {
  if (reason === 'not_configured') return 'AI is not connected. This explanation uses verified match facts.'
  if (reason === 'offline') return 'Offline mode is active. This explanation uses verified match facts.'
  if (reason === 'timeout') return 'AI took too long. Verified match facts keep the replay available.'
  if (reason === 'injected_client') return 'This is a test-generated selection, not a live AI response.'
  return 'AI output is unavailable or could not be verified. Showing an evidence-based explanation.'
}
function GenerationNotice({ value, preview }: { value: IntelligenceFields & { source: string }; preview: boolean }) {
  const metadata = value.metadata ?? value.narrative?.metadata
  return <div className="generation-notice" data-testid="generation-notice">
    <span className="source-tag">{preview ? 'Preview template' : source(value.source)}</span>
    <p>{preview ? 'Local fictional sample · no AI request.' : value.source === 'foundry'
      ? 'Microsoft Foundry selected supported facts and framing. Wording is rendered from verified evidence.'
      : fallbackMessage(metadata?.fallback_reason)}</p>
  </div>
}
function factLabel(fact: Fact): string {
  if (fact.id.startsWith('goals_before_')) return 'Goals before'
  if (fact.id.startsWith('goals_after_')) return 'Goals after'
  return ({ score_before: 'Score before', score_after: 'Score after', final_score: 'Final score',
    goal_count: 'Goals', shot_count: 'Shots', pass_count: 'Passes', possession_available: 'Measured possession', possession_percent: 'Measured possession',
    possession_change_points: 'Possession change', scorer_name: 'Scorer' } as Record<string, string>)[fact.metric] ?? 'Recorded fact'
}
function factValue(fact: Fact, context: ContextPacket): string | null {
  if (fact.id === 'possession_available' || fact.metric === 'possession_available') return fact.value === 0 ? 'Unavailable' : 'Available'
  if (typeof fact.value === 'number') return String(fact.value) + ((fact.unit === 'percent' || fact.unit === '%') ? '%' : fact.unit === 'percentage_points' ? ' percentage points' : '')
  if (typeof fact.value === 'string') return fact.value
  if (fact.value && !Array.isArray(fact.value) && typeof fact.value === 'object'
    && Object.keys(fact.value).every(team => team in context.teams && typeof (fact.value as Record<string, unknown>)[team] === 'number')) {
    return Object.entries(fact.value).map(([team, value]) => `${context.teams[team]} ${value}`).join(' · ')
  }
  return null
}
function AnalystFacts({ narrative }: { narrative: NarrativeResult }) {
  const context = narrative.evidence
  const selected = new Set(narrative.selected_fact_ids)
  const possessionUnavailable = context.facts.some(fact => (fact.id === 'possession_available' || fact.metric === 'possession_available') && fact.value === 0)
  const facts = context.facts.filter(fact => selected.has(fact.id) && !(possessionUnavailable && fact.metric === 'possession_percent') && factValue(fact, context) !== null)
  return <div className="analyst-facts" data-testid="analyst-facts"><strong>Recorded facts and windows</strong>
    <dl>{facts.map(fact => <div key={fact.id}><dt>{factLabel(fact)}{fact.team_id ? ' · ' + context.teams[fact.team_id] : ''}
      {fact.window ? <small>Minutes {fact.window.start}–{fact.window.end}, inclusive</small> : null}</dt>
      <dd>{factValue(fact, context)}</dd></div>)}</dl>
  </div>
}
function StatComparison({ label, left, right, suffix, home, away, available = true }: { label: string; left: number; right: number; suffix: string; home: Team; away: Team; available?: boolean }) {
  if (!available) return <div className="stat"><div><span>{label}</span><strong>Unavailable</strong></div><p>No recorded possession changes; initial-holder allocation is an assumption.</p></div>
  return <div className="stat"><div><strong>{left}{suffix}</strong><span>{label}</span><strong>{right}{suffix}</strong></div><div className="stat-track" role="img" aria-label={label + ': ' + home.name + ' ' + left + suffix + ', ' + away.name + ' ' + right + suffix}><span style={{ width: (left + right ? left / (left + right) * 100 : 50) + '%' }} /></div></div>
}
function Limitations({ values }: { values: string[] }) {
  return values.length ? <div className="insight-limitations"><strong>Evidence limits</strong><ul>{values.map(value => <li key={value}>{value}</li>)}</ul></div> : null
}
function StudioOverlay({ overlay, minute, preview }: { overlay: Overlay | null | undefined; minute: number; preview: boolean }) {
  const usable = overlay && overlay.synthetic === true && overlay.match_minute <= minute
  return <section className="studio-panel" aria-labelledby="studio-title" data-testid="studio-preview">
    <div className="section-head"><div><h2 id="studio-title">Studio graphic preview</h2><p>A timed graphic for the selected fictional moment</p></div>
      <span className="studio-label">Synthetic match data</span></div>
    {usable ? <><div className="studio-canvas"><div className="studio-graphic" data-testid="studio-graphic">
      <span className="studio-minute">{overlay.match_minute}′ · {preview ? 'Local preview' : 'Recorded moment'}</span>
      <strong>{overlay.headline}</strong><p>{overlay.stat_line}</p><span className="studio-synthetic">Synthetic match data</span>
    </div></div><p className="studio-caption">Suggested display: {overlay.display_duration_ms / 1000} seconds · {overlay.priority === 'high' ? 'High' : overlay.priority === 'medium' ? 'Medium' : 'Low'} priority. Replay at minute {minute}.</p></>
      : <p className="studio-empty">Choose an insight to preview its studio graphic.</p>}
  </section>
}
function App() {
  const [minute, setMinute] = useState(0)
  const [previewMode, setPreviewMode] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState<(typeof speeds)[number]>(1)
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [snapshotLoading, setSnapshotLoading] = useState(true)
  const [snapshotError, setSnapshotError] = useState<string | null>(null)
  const [snapshotAttempt, setSnapshotAttempt] = useState(0)
  const [mode, setMode] = useState<Mode>('fan')
  const [preferredTeam, setPreferredTeam] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [explanationState, setExplanationState] = useState<LoadState<Explanation> | null>(null)
  const [explanationAttempt, setExplanationAttempt] = useState(0)
  const [recapState, setRecapState] = useState<LoadState<Recap> | null>(null)
  const [recapAttempt, setRecapAttempt] = useState(0)
  const snapshots = useRef(new Map<number, Snapshot>())
  const explanations = useRef(new Map<string, CacheEntry<Explanation>>())
  const recaps = useRef(new Map<string, CacheEntry<Recap>>())

  useEffect(() => {
    if (!playing) return
    const timer = window.setInterval(() => setMinute(current => Math.min(90, current + 1)), 2000 / speed)
    return () => window.clearInterval(timer)
  }, [playing, speed])
  useEffect(() => { if (minute === 90) setPlaying(false) }, [minute])

  useEffect(() => {
    if (previewMode) { setSnapshot(demoSnapshot(minute)); setSnapshotError(null); setSnapshotLoading(false); return }
    const cached = snapshots.current.get(minute)
    if (cached) { setSnapshot(cached); setSnapshotError(null); setSnapshotLoading(false); return }
    const controller = new AbortController()
    setSnapshotLoading(true)
    setSnapshotError(null)
    request<Snapshot>(base + '?minute=' + minute, controller.signal).then(data => {
      if (controller.signal.aborted) return
      if (!isSnapshot(data) || data.minute !== minute) throw new Error('Invalid match snapshot')
      snapshots.current.set(minute, data)
      setSnapshot(data)
      setSnapshotLoading(false)
    }).catch((error: unknown) => {
      if (controller.signal.aborted) return
      setPlaying(false)
      setSnapshotError(error instanceof Error ? error.message : 'Match data could not be loaded')
      setSnapshotLoading(false)
    })
    return () => controller.abort()
  }, [minute, snapshotAttempt, previewMode])

  const current = previewMode ? demoSnapshot(minute) : snapshot?.minute === minute ? snapshot : null
  // Keep controls mounted while the next API snapshot loads; all stale details
  // are hidden and the retained panel is explicitly labelled with its own minute.
  const display = previewMode ? current : snapshot
  const displayMinute = display?.minute ?? minute
  const selected = current?.insights.find(insight => insight.id === selectedId)
  const version = current?.fixture_version
  const sourceKey = previewMode ? 'preview' : 'api'
  useEffect(() => {
    if (display && preferredTeam && !display.teams.some(team => team.id === preferredTeam)) setPreferredTeam('')
  }, [display?.fixture_version, preferredTeam])
  const explanationKey = selected && version ? [sourceKey, version, selected.id, mode].join(':') : null
  const explanation = explanationState?.key === explanationKey ? explanationState.value : null
  const explanationError = explanationState?.key === explanationKey ? explanationState.error : null
  const explanationLoading = !!selected && !explanation && !explanationError
  useEffect(() => {
    if (!selected || !version || !explanationKey) return
    if (previewMode) { setExplanationState({ key: explanationKey, value: demoExplanation(selected, mode), error: null }); return }
    const key = explanationKey
    const cached = explanations.current.get(key)
    if (cached && cached.expires > Date.now()) { setExplanationState({ key, value: cached.value, error: null }); return }
    explanations.current.delete(key)
    const controller = new AbortController()
    setExplanationState({ key, value: null, error: null })
    request<Explanation>(base + '/insights/' + encodeURIComponent(selected.id) + '?mode=' + mode + '&as_of_minute=' + minute, controller.signal).then(data => {
      if (controller.signal.aborted) return
      if (data.insight_id !== selected.id || data.mode !== mode || !data.text || !data.evidence) throw new Error('Invalid insight explanation')
      const duration = cacheDuration(data)
      if (duration) explanations.current.set(key, { value: data, expires: Date.now() + duration })
      setExplanationState({ key, value: data, error: null })
    }).catch((error: unknown) => {
      if (controller.signal.aborted) return
      setExplanationState({ key, value: null, error: error instanceof Error ? error.message : 'Explanation could not be loaded' })
    })
    return () => controller.abort()
  }, [selected?.id, version, mode, explanationAttempt, previewMode, explanationKey])

  const recapKey = minute === 90 && version ? [sourceKey, version, mode, 'recap'].join(':') : null
  const recap = recapState?.key === recapKey ? recapState.value : null
  const recapError = recapState?.key === recapKey ? recapState.error : null
  const recapLoading = !!recapKey && !recap && !recapError
  useEffect(() => {
    if (!recapKey || !version) return
    if (previewMode) { setRecapState({ key: recapKey, value: demoRecap(mode), error: null }); return }
    const key = recapKey
    const cached = recaps.current.get(key)
    if (cached && cached.expires > Date.now()) { setRecapState({ key, value: cached.value, error: null }); return }
    recaps.current.delete(key)
    const controller = new AbortController()
    setRecapState({ key, value: null, error: null })
    request<Recap>(base + '/recap?mode=' + mode + '&as_of_minute=90', controller.signal).then(data => {
      if (controller.signal.aborted) return
      if (data.mode !== mode || !data.text || !data.final_score || !data.stats) throw new Error('Invalid full-time recap')
      const duration = cacheDuration(data)
      if (duration) recaps.current.set(key, { value: data, expires: Date.now() + duration })
      setRecapState({ key, value: data, error: null })
    }).catch((error: unknown) => {
      if (controller.signal.aborted) return
      setRecapState({ key, value: null, error: error instanceof Error ? error.message : 'Recap could not be loaded' })
    })
    return () => controller.abort()
  }, [version, mode, recapAttempt, previewMode, recapKey])

  function seek(target: number) { setPlaying(false); setMinute(Math.max(0, Math.min(90, target))) }
  function changeSource(preview: boolean) {
    setPlaying(false)
    setSelectedId(null)
    if (preview !== previewMode) { setSnapshot(null); setPreferredTeam('') }
    setPreviewMode(preview)
  }
  const teams = display?.teams ?? []
  const home = teams[0]
  const away = teams[1]
  const insightList = prioritizeInsights(display?.insights ?? [], TEAM_FOCUS_ENABLED ? preferredTeam : null)
  const eventList = [...(display?.recent_events ?? [])].reverse()
  const candidateOverlay = current ? (selected ? explanation?.overlay : recap?.overlay) : null
  const overlay = candidateOverlay && (!selected || candidateOverlay.insight_id === selected.id) ? candidateOverlay : null
  return <div className="app-shell">
    <header className="site-header">
      <a href="#match" className="brand"><span className="brand-symbol" aria-hidden="true">◉</span><span>AFTER<span className="brand-accent">90</span></span></a>
      <nav className="site-nav" aria-label="Dashboard sections"><a href="#match">Match center</a><a href="#insights-title">Insights</a><a href="#activity-title">Activity</a><a href="#studio-title">Studio</a></nav>
      <span className="synthetic-label">Synthetic match data</span>
    </header>
    <main id="match" className="dashboard">
      <div className="page-intro"><div><span className="eyebrow">THE FUTURE OF MATCH INTELLIGENCE</span><h1>Every moment. <span>Explained.</span></h1><p>Explore a fictional football match through evidence-backed insights, replay and personalized explanations.</p></div><div className="data-mode"><span className="mode-label">DATA SOURCE</span><div className="data-toggle" role="group" aria-label="Match data source"><button className={!previewMode ? 'active' : ''} aria-pressed={!previewMode} onClick={() => changeSource(false)}>Team API</button><button className={previewMode ? 'active' : ''} aria-pressed={previewMode} onClick={() => changeSource(true)}>Local preview</button></div><small>{previewMode ? 'Small sample dataset · template explanations · no live AI' : 'Verified fictional events from the match API'}</small></div></div>
      <section className="match-hero" aria-labelledby="match-title">
        <div className="hero-top"><p id="match-title">MATCH CENTER <span className="hero-live-dot">●</span> {previewMode ? 'LOCAL PREVIEW' : 'API REPLAY'}</p><span>{current ? 'Minute ' + current.minute : 'Awaiting minute ' + minute}</span></div>
        {current ? <div className="scoreboard" aria-label={home.name + ' ' + current.score[home.id] + ', ' + away.name + ' ' + current.score[away.id]}>
          <div className="team"><span className="crest home-crest" aria-hidden="true">N</span><h1>{home.name}</h1><small>Home</small></div>
          <div className="score-center"><div className="score"><span>{current.score[home.id]}</span><i>:</i><span>{current.score[away.id]}</span></div><span className="clock">{minute === 90 ? 'Full time' : String(minute).padStart(2, '0') + ':00'}</span></div>
          <div className="team"><span className="crest away-crest" aria-hidden="true">C</span><h1>{away.name}</h1><small>Away</small></div>
        </div> : <div className="hero-state" role={snapshotError ? 'alert' : 'status'}><h1>{snapshotError ? 'Match data unavailable' : 'Loading match'}</h1><p>{snapshotError ? 'The match API could not be reached. Check the connection, then retry.' : 'Getting minute ' + minute + '.'}</p>{snapshotError && <button onClick={() => setSnapshotAttempt(n => n + 1)}>Retry match data</button>}</div>}
        <div className="pitch-rule" aria-hidden="true" />
      </section>
      <section className="replay-panel" aria-labelledby="replay-title"><div className="replay-head"><div><h2 id="replay-title">Match replay <span className="section-spark">✦</span></h2><p>Jump to any match minute</p></div><strong>{minute}' <small>/ 90'</small></strong></div>
        <label htmlFor="minute-slider" className="sr-only">Match minute</label><input id="minute-slider" className="minute-slider" type="range" min="0" max="90" value={minute} onChange={event => seek(Number(event.target.value))} style={{ '--progress': minute / 90 * 100 + '%' } as React.CSSProperties} />
        <div className="timeline-labels"><span>Kick off</span><span>Half time</span><span>Full time</span></div>
        <div className="transport"><div className="transport-buttons"><button className="primary-button" disabled={snapshotLoading || !!snapshotError} onClick={() => minute === 90 ? seek(0) : setPlaying(value => !value)} aria-label={minute === 90 ? 'Replay from start' : playing ? 'Pause replay' : 'Play replay'}>{minute === 90 ? '↺ Replay' : playing ? 'Ⅱ Pause' : '▶ Play'}</button><button onClick={() => seek(0)} disabled={minute === 0}>Reset</button><button onClick={() => seek(90)} disabled={minute === 90}>Jump to full time</button></div><div className="speed-group" aria-label="Replay speed"><span>Speed</span>{speeds.map(value => <button key={value} aria-pressed={speed === value} className={speed === value ? 'active' : ''} onClick={() => setSpeed(value)}>{value}×</button>)}</div></div>
      </section>
      {display && <section className="stats-panel" aria-labelledby="stats-title" aria-busy={!current}><div className="section-head"><h2 id="stats-title">Match intelligence</h2><p>{!current ? 'Previous snapshot · ' : ''}Through minute {displayMinute}</p></div><div className="stats-grid">{([['Possession', 'possession_percent', '%'], ['Shots', 'shots', ''], ['Passes', 'passes', '']] as const).map(([label, key, suffix]) => {
          const left = display.stats[key][home.id] ?? 0
          const right = display.stats[key][away.id] ?? 0
          return <StatComparison key={key} label={label} left={left} right={right} suffix={suffix} home={home} away={away} available={key !== 'possession_percent' || display.possession_available !== false} />
        })}</div></section>}
      {display && <MatchActivity key={sourceKey + ':' + display.fixture_version} events={display.recent_events} teams={teams} minute={displayMinute} onSeek={seek} loading={!current} />}
      {display && <>
        <div className="content-grid">
          <section className="insights-panel" aria-labelledby="insights-title" aria-busy={!current}><div className="section-head insight-head"><div><h2 id="insights-title">✦ Insight center</h2><p>{!current ? 'Updating replay · previous snapshot at minute ' + displayMinute : mode === 'fan' ? 'The match story in plain language' : 'Exact facts, comparisons and evidence windows'}</p></div><div className="mode-switch" role="group" aria-label="Explanation mode"><button aria-pressed={mode === 'fan'} className={mode === 'fan' ? 'active' : ''} onClick={() => setMode('fan')}>Fan</button><button aria-pressed={mode === 'analyst'} className={mode === 'analyst' ? 'active' : ''} onClick={() => setMode('analyst')}>Analyst</button></div></div>
            {TEAM_FOCUS_ENABLED && display && <div className="team-focus"><label htmlFor="team-focus">Prioritize a team</label><select id="team-focus" value={preferredTeam} onChange={event => setPreferredTeam(event.target.value)}><option value="">All teams · latest first</option>{teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}</select><small>Changes story order only. Facts and evidence stay the same.</small></div>}
            {insightList.length === 0 ? <div className="empty-state"><strong>No insights yet</strong><p>Play or jump ahead to see evidence-backed moments.</p></div> : <div className="insight-list">{insightList.map(insight => <article className={'insight-card ' + (selectedId === insight.id ? 'selected' : '')} key={sourceKey + ':' + display.fixture_version + ':' + insight.id}><button className="insight-select" aria-expanded={selectedId === insight.id} aria-controls={'detail-' + insight.id} aria-disabled={!current} onClick={() => { if (current) setSelectedId(selectedId === insight.id ? null : insight.id) }}><span className={'insight-icon ' + insight.type} aria-hidden="true">{insight.type === 'goal' ? '●' : insight.type === 'shot_surge' ? '↗' : '↔'}</span><span className="insight-summary"><small>{insight.minute}' · {teams.find(team => team.id === insight.team_id)?.name ?? insight.team_id}</small><strong>{title(insight)}</strong><small>{insight.evidence_event_ids.length} supporting events</small></span><span className="open-icon" aria-hidden="true">{selectedId === insight.id ? '−' : '+'}</span></button>{selectedId === insight.id && <div className="insight-detail" id={'detail-' + insight.id}>
              <div className="explanation" aria-live="polite" data-testid="insight-explanation">{!current || explanationLoading ? <p role="status">Loading {mode} explanation…</p> : explanationError ? <div role="alert"><p>The explanation could not be loaded. Verified evidence remains available.</p><button className="text-button" onClick={() => setExplanationAttempt(n => n + 1)}>Retry explanation</button></div> : explanation ? <>
                {(explanation.headline ?? explanation.narrative?.headline) && <h3>{explanation.headline ?? explanation.narrative?.headline}</h3>}<p>{explanation.text}</p><GenerationNotice value={explanation} preview={previewMode} />{!previewMode && explanation.source === 'template' && <button className="text-button" onClick={() => setExplanationAttempt(n => n + 1)}>Refresh explanation</button>}
                {mode === 'analyst' && explanation.narrative && <AnalystFacts narrative={explanation.narrative} />}
                <Limitations values={explanation.limitations ?? explanation.narrative?.limitations ?? []} />
              </> : null}</div>
              {current && <details className="evidence-disclosure" open={mode === 'analyst'}><summary>View supporting evidence</summary><Evidence insight={insight} teams={teams} /></details>}
            </div>}</article>)}</div>}
          </section>
          <section className="events-panel" aria-labelledby="events-title"><div className="section-head"><h2 id="events-title">Match timeline</h2><p>{!current ? 'Previous snapshot · ' : ''}Latest events through minute {displayMinute}</p></div>{eventList.length === 0 ? <div className="empty-state"><strong>No recent recorded events</strong><p>Events appear as the replay advances.</p></div> : <ol className="event-list" tabIndex={0} aria-label="Recent recorded match events">{eventList.map(event => <li key={event.id} className={event.type === 'goal' ? 'goal-event' : ''}><time>{event.minute}'{String(event.second).padStart(2, '0')}″</time><span className="event-dot" aria-hidden="true" /><div><strong>{eventTitle(event)}</strong><p>{teams.find(team => team.id === event.team_id)?.name ?? event.team_id}{event.player_id ? ' · ' + event.player_id : ''}</p><small>{event.id}{event.related_event_id ? ' · linked shot ' + event.related_event_id : ''}</small></div></li>)}</ol>}</section>
        </div>
        <StudioOverlay overlay={overlay} minute={minute} preview={previewMode} />
        {minute === 90 && current && <section className="recap-panel" aria-labelledby="recap-title" data-testid="full-time-recap"><div className="recap-head"><div><span>90'</span><h2 id="recap-title">Full-time recap</h2></div><small>{mode === 'fan' ? 'Fan view' : 'Analyst view'}</small></div>{recapLoading ? <p role="status">Loading full-time recap…</p> : recapError ? <div role="alert"><p>The recap could not be loaded. Final match numbers remain available above.</p><button className="text-button" onClick={() => setRecapAttempt(n => n + 1)}>Retry recap</button></div> : recap ? <><p className="recap-text">{recap.text}</p>{recap.possession_available === false && <p>Measured possession is unavailable: no possession-change events were recorded; initial-holder allocation is an assumption.</p>}<GenerationNotice value={recap} preview={previewMode} />{!previewMode && recap.source === 'template' && <button className="text-button" onClick={() => setRecapAttempt(n => n + 1)}>Refresh recap</button>}{mode === 'analyst' && recap.narrative && <AnalystFacts narrative={recap.narrative} />}<Limitations values={recap.limitations ?? recap.narrative?.limitations ?? []} /><div className="recap-meta"><span>{recap.moment_ids.length ? 'Based on insights: ' + recap.moment_ids.join(', ') : 'Based on final match facts'}</span></div></> : null}</section>}
      </>}
    </main><footer className="site-footer"><span>AFTER90 · Understand every moment</span><span>{previewMode ? 'Local fictional preview · no live AI' : 'Synthetic match data · Team API'}</span></footer>
  </div>
}
export default App
