// API client — reads from /api/* (proxied to FastAPI by Vite dev server).
// All components stay on fixture types; Phase 2 just swaps the data source.

import type { Brief, ThemeReport, ScheduleSettings, RunRecord, BusinessMeta, MetricsData, EvalData } from './types'

const BASE = '/api'

// Static demo build (VITE_DEMO=1): answer from bundled simulated JSON instead
// of the API. The JSON is a separate chunk, so normal builds never ship it.
export const DEMO = import.meta.env.VITE_DEMO === '1'

async function demoGet(path: string): Promise<unknown> {
  const data = (await import('./demo-data.json')).default
  const url = new URL(path, 'https://demo.invalid')
  const forBiz = (table: object) =>
    (table as Record<string, unknown>)[url.searchParams.get('business_id') ?? '']
  switch (url.pathname) {
    case '/businesses': return data.businesses
    case '/brief': return (forBiz(data.briefs) as Record<string, unknown> | undefined)?.[url.searchParams.get('week') ?? '']
    case '/schedule': return forBiz(data.schedules)
    case '/runs': return forBiz(data.runs)
    case '/metrics': return data.metrics
    case '/eval': return { available: false }   // EvalTab falls back to the real eval fixture
  }
  throw new Error(`demo: no data for ${path}`)
}

async function get<T>(path: string): Promise<T> {
  if (DEMO) return demoGet(path) as Promise<T>
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

async function put<T>(path: string, body: unknown): Promise<T> {
  if (DEMO) throw new Error('demo is read-only')
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`API PUT ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

export const api = {
  businesses: (): Promise<BusinessMeta[]> =>
    get('/businesses'),

  brief: (businessId: string, week: string): Promise<{ brief: Brief; themeReport: ThemeReport }> =>
    get(`/brief?business_id=${encodeURIComponent(businessId)}&week=${encodeURIComponent(week)}`),

  schedule: (businessId: string): Promise<ScheduleSettings> =>
    get(`/schedule?business_id=${encodeURIComponent(businessId)}`),

  saveSchedule: (settings: ScheduleSettings): Promise<ScheduleSettings> =>
    put('/schedule', settings),

  runs: (businessId: string): Promise<RunRecord[]> =>
    get(`/runs?business_id=${encodeURIComponent(businessId)}`),

  metrics: (): Promise<MetricsData> =>
    get('/metrics'),

  eval: (): Promise<EvalData> =>
    get('/eval'),
}
