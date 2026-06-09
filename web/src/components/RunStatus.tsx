import type { RunRecord, ScheduleSettings, Brief } from '../types'

interface RunStatusProps {
  runs: RunRecord[]
  schedule: ScheduleSettings
  brief: Brief
}

function relativeTime(iso: string): string {
  const d = new Date(iso)
  const diffMs = Date.now() - d.getTime()
  const days = Math.floor(diffMs / 86400000)
  if (days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days} days ago`
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function nextRunDate(schedule: ScheduleSettings): string {
  if (schedule.cadence === 'off') return 'Off'
  const days = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']
  const targetIdx = days.indexOf(schedule.day_of_week)
  const now = new Date()
  let delta = (targetIdx - now.getDay() + 7) % 7
  if (delta === 0) delta = 7
  const next = new Date(now)
  next.setDate(now.getDate() + delta)
  return next.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' })
}

function duration(a: string, b: string): string {
  const secs = Math.round((new Date(b).getTime() - new Date(a).getTime()) / 1000)
  if (secs < 60) return `${secs}s`
  return `${Math.floor(secs / 60)}m ${secs % 60}s`
}

export default function RunStatus({ runs, schedule, brief }: RunStatusProps) {
  const latest = runs[0]

  return (
    <section
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--line)',
        borderRadius: 'var(--radius)',
        boxShadow: 'var(--shadow)',
      }}
      aria-label="Automation status"
    >
      <div style={{ padding: '18px 20px 0' }}>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 17, fontWeight: 600 }}>
          Automation
        </h2>
      </div>

      <div style={{ padding: '16px 20px 20px' }}>
        {brief.partial && (
          <div
            role="alert"
            style={{
              background: '#FEF3E2',
              border: '1px solid var(--mix)',
              borderRadius: 8,
              padding: '8px 10px',
              marginBottom: 14,
              fontSize: 12,
              color: 'var(--ink)',
              lineHeight: 1.4,
            }}
          >
            <strong>Partial data</strong> — some classification batches failed.
          </div>
        )}

        {latest ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' as const }}>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: 11,
                  fontWeight: 800,
                  letterSpacing: '.06em',
                  textTransform: 'uppercase' as const,
                  padding: '4px 10px',
                  borderRadius: 999,
                  color: latest.status === 'success' ? 'var(--pos)' : latest.status === 'partial' ? 'var(--mix)' : 'var(--neg)',
                  background: latest.status === 'success' ? 'var(--pos-soft)' : latest.status === 'partial' ? 'var(--mix-soft)' : 'var(--neg-soft)',
                }}
              >
                ● {latest.status === 'success' ? 'Success' : latest.status === 'partial' ? 'Partial' : 'Failed'}
              </span>
              <span style={{ fontSize: 12, color: 'var(--ink-faint)' }}>
                Last run {relativeTime(latest.finished_at)}
              </span>
            </div>

            {/* Stats row */}
            <div
              style={{
                display: 'flex',
                gap: 18,
                marginTop: 14,
                paddingTop: 14,
                borderTop: '1px solid var(--line)',
              }}
            >
              {[
                { n: `$${latest.total_cost_usd.toFixed(3)}`, k: 'Cost' },
                { n: duration(latest.started_at, latest.finished_at), k: 'Duration' },
                { n: `${latest.batches_total - latest.batches_failed}/${latest.batches_total}`, k: 'Batches' },
              ].map(({ n, k }) => (
                <div key={k}>
                  <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 600, color: 'var(--ink)' }}>
                    {n}
                  </div>
                  <div style={{ fontSize: 10, letterSpacing: '.1em', textTransform: 'uppercase' as const, color: 'var(--ink-faint)', marginTop: 2 }}>
                    {k}
                  </div>
                </div>
              ))}
            </div>

            {/* Next run */}
            {schedule.cadence !== 'off' && (
              <div
                style={{
                  fontSize: 12,
                  color: 'var(--ink-soft)',
                  marginTop: 14,
                  paddingTop: 12,
                  borderTop: '1px solid var(--line)',
                }}
              >
                Next scheduled run · <strong style={{ color: 'var(--ink)' }}>{nextRunDate(schedule)}</strong>
              </div>
            )}
          </>
        ) : (
          <p style={{ fontSize: 13, color: 'var(--ink-faint)' }}>No runs yet.</p>
        )}
      </div>
    </section>
  )
}
