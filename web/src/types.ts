// Contract types — mirror docs/CONTRACTS.md exactly.
// Phase 1 UI agent builds all components against these shapes.

export interface Review {
  review_id: string
  business_id: string
  business_name: string
  stars: number
  text: string
  date: string
  week: string
}

export interface Theme {
  theme_id: string
  label: string
  sentiment: 'positive' | 'negative' | 'mixed'
  review_ids: string[]
  count: number
  sample_quotes: string[]
}

export interface ThemeReport {
  business_id: string
  week: string
  review_count: number
  avg_stars: number
  prev_avg_stars: number | null
  themes: Theme[]
  sufficient: boolean
  partial: boolean
}

export interface ActionItem {
  rank: number
  theme_id: string
  headline: string
  why_it_matters: string
  recommended_action: string
  evidence_review_ids: string[]
  severity: 'high' | 'medium' | 'low'
}

export interface Brief {
  business_id: string
  business_name: string
  week: string
  summary: string
  trend: 'up' | 'down' | 'flat'
  action_items: ActionItem[]
  email_draft: string | null
  partial: boolean
  generated_by: string
}

export interface ScheduleSettings {
  business_id: string
  cadence: 'weekly' | 'biweekly' | 'off'
  day_of_week: 'mon' | 'tue' | 'wed' | 'thu' | 'fri' | 'sat' | 'sun'
  email_mode: 'auto_send' | 'draft_only'
}

export interface RunRecord {
  run_id: string
  business_id: string
  week: string
  status: 'success' | 'partial' | 'failed'
  started_at: string
  finished_at: string
  total_cost_usd: number
  batches_total: number
  batches_failed: number
  note: string | null
}

export interface BusinessMeta {
  business_id: string
  business_name: string
  weeks: string[]
}

// Phase 4: cost/metrics endpoint

export interface ModelMetrics {
  calls: number
  total_cost_usd: number
  avg_latency_ms: number
  p95_latency_ms: number
  total_input_tokens: number
  total_output_tokens: number
  cache_read_tokens: number
  cache_creation_tokens: number
  prompt_cache_saved_usd: number
}

export interface StageMetrics {
  calls: number
  total_cost_usd: number
  avg_latency_ms: number
}

export interface RoutingMix {
  haiku_pct: number
  sonnet_pct: number
  opus_pct: number
}

export interface MetricsData {
  total_cost_usd: number
  total_calls: number
  by_model: Record<string, ModelMetrics>
  by_stage: Record<string, StageMetrics>
  routing_mix: RoutingMix
  idempotency_skips: number
  days_covered: number
  generated_at: string
}

// Quality-vs-cost eval (Phase 5) — one scored run per model tier against the
// human-signed-off golden set. Served by GET /api/eval (static artifact).
export interface EvalRow {
  model: string
  label: string
  cost_usd: number
  label_f1: number
  label_precision: number
  label_recall: number
  evidence_overlap: number
  sentiment_accuracy: number
  matched_themes: number
  total_golden_themes: number
}

export interface EvalData {
  available: boolean
  business_id?: string
  week?: string
  business_name?: string
  review_count?: number
  golden_themes?: number
  note?: string
  generated_at?: string
  rows?: EvalRow[]
}
