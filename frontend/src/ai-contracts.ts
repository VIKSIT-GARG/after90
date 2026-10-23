// Proposed AI v1.0 contracts. The existing endpoints remain backward compatible.
export type InterpretationCode =
  | 'GOAL_OPENS_SCORING' | 'GOAL_EQUALIZES' | 'GOAL_TAKES_LEAD'
  | 'GOAL_EXTENDS_LEAD' | 'GOAL_REDUCES_DEFICIT' | 'GOAL_RECORDED'
  | 'SHOT_SURGE' | 'POSSESSION_INCREASE' | 'LIMITED_EVIDENCE' | 'MATCH_RECAP'
export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue }
export type InclusiveWindow = { start: number; end: number }
export type Fact = {
  id: string; metric: string; value: number | string | JsonValue[] | { [key: string]: JsonValue }
  team_id?: string | null; player_id?: string | null; unit?: string | null; window?: InclusiveWindow | null
}
export type ContextPacket = {
  schema_version: '1.0'; match_id: string; fixture_version: string; insight_id: string
  insight_type: 'goal' | 'shot_surge' | 'possession_swing' | 'recap' | 'limited_evidence'
  minute: number; as_of_minute: number; team_id?: string | null; teams: Record<string, string>
  facts: Fact[]; evidence_event_ids: string[]; supported_interpretations: InterpretationCode[]; limitations: string[]
}
// Model-authored bounded selection, not arbitrary factual prose.
export type NarrativeSelection = {
  selected_fact_ids: string[]; interpretation_code: InterpretationCode
  fan_frame: 'concise' | 'contextual'; analyst_frame: 'evidence' | 'comparison'; limitations: string[]
}
// Wording rendered by the server from validated selection and authoritative facts.
export type NarrativeOutput = {
  headline: string; selected_fact_ids: string[]; interpretation_code: InterpretationCode
  fan_explanation: string; analyst_explanation: string; limitations: string[]
}
export type GenerationMetadata = {
  source: 'foundry' | 'template'; fallback_reason: string | null
  model_version: string; prompt_version: string; latency_ms: number
}
export type Overlay = {
  insight_id: string; match_minute: number; headline: string; stat_line: string
  display_duration_ms: number; priority: 'low' | 'medium' | 'high'; evidence_event_ids: string[]
  source: 'foundry' | 'template'; synthetic: true
}
export type ValidationMetadata = {
  passed: boolean; reason: string | null; transport: 'foundry' | 'injected' | 'offline'
}
export type NarrativeResult = NarrativeOutput & {
  source: 'foundry' | 'template'; selection_source: 'foundry' | 'injected' | 'deterministic'
  selection_accepted: boolean; selection: NarrativeSelection; metadata: GenerationMetadata
  validation: ValidationMetadata; evidence: ContextPacket
}
