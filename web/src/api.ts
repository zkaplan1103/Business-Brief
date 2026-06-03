// API client — reads from /api/* (proxied to FastAPI by Vite dev server).
// All components stay on fixture types; Phase 2 just swaps the data source.

import type { Brief, ThemeReport, ScheduleSettings, RunRecord, BusinessMeta } from './types'

const BASE = '/api'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

async function put<T>(path: string, body: unknown): Promise<T> {
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
}
