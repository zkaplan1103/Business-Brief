import type { RunRecord, ScheduleSettings, Brief } from '../types'

interface RunStatusProps {
  runs: RunRecord[]
  schedule: ScheduleSettings
  brief: Brief
}

const statusStyles: Record<string, { color: string; bg: string; label: string }> = {
  success: { color: 'var(--accent-1)', bg: 'color-mix(in srgb, var(--accent-1) 10%, var(--surface))', label: 'Success' },
  partial: { color: 'var(--accent-2)', bg: 'var(--partial-bg)', label: 'Partial' },
  failed: { color: 'var(--sev-high)', bg: 'color-mix(in srgb, var(--sev-high) 8%, var(--surface))', label: 'Failed' },
}

const DAY_LABELS: Record<string, string> = {
  mon: 'Monday', tue: 'Tuesday', wed: 'Wednesday',
  thu: 'Thursday', fri: 'Friday', sat: 'Saturday', sun: 'Sunday',
}

function formatRelativeTime(iso: string): string {
  const date = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays} days ago`
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatDuration(startIso: string, endIso: string): string {
  const start = new Date(startIso).getTime()
  const end = new Date(endIso).getTime()
  const diffSecs = Math.round((end - start) / 1000)
  if (diffSecs < 60) return `${diffSecs}s`
  const mins = Math.floor(diffSecs / 60)
  const secs = diffSecs % 60
  return `${mins}m ${secs}s`
}

function getNextRunDate(schedule: ScheduleSettings): string {
  if (schedule.cadence === 'off') return 'Scheduling is off'
  const days = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']
  const targetDayIdx = days.indexOf(schedule.day_of_week)
  const now = new Date()
  const currentDayIdx = now.getDay()
  let daysUntil = (targetDayIdx - currentDayIdx + 7) % 7
  if (daysUntil === 0) daysUntil = 7 // next week
  const nextRun = new Date(now)
  nextRun.setDate(now.getDate() + daysUntil)
  return nextRun.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' })
}

export default function RunStatus({ runs, schedule, brief }: RunStatusProps) {
  const latest = runs[0]

  return (
    <section
      style={{
        background: 'var(--surface)',
        borderRadius: 'var(--radius)',
        boxShadow: 'var(--shadow-card)',
        padding: '16px 20px',
      }}
      aria-label="Run status"
    >
      {/* Partial data warning */}
      {brief.partial && (
        <div
          style={{
            background: 'var(--partial-bg)',
            border: '1px solid var(--accent-2)',
            borderRadius: 'var(--radius)',
            padding: '8px 12px',
            marginBottom: 14,
            display: 'flex',
            gap: 8,
            alignItems: 'flex-start',
          }}
          role="alert"
        >
          <span style={{ fontSize: 15 }}>⚠</span>
          <p
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 13,
              color: 'var(--text)',
              lineHeight: 1.4,
              margin: 0,
            }}
          >
            <strong>Based on partial data.</strong> Some classification batches failed — this brief was produced from the batches that succeeded.
          </p>
        </div>
      )}

      <div
        style={{
          fontFamily: 'var(--font-body)',
          fontSize: 11,
          fontWeight: 600,
          color: 'var(--text-muted)',
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          marginBottom: 10,
        }}
      >
        Automation Status
      </div>

      {latest ? (
        <div className="flex flex-col gap-3">
          {/* Last run */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              gap: 12,
              flexWrap: 'wrap',
            }}
          >
            <div>
              <div
                style={{
                  fontFamily: 'var(--font-body)',
                  fontSize: 12,
                  color: 'var(--text-muted)',
                  marginBottom: 4,
                }}
              >
                Last run
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <span
                  style={{
                    fontFamily: 'var(--font-body)',
                    fontSize: 12,
                    fontWeight: 600,
                    letterSpacing: '0.04em',
                    textTransform: 'uppercase',
                    color: statusStyles[latest.status].color,
                    background: statusStyles[latest.status].bg,
                    borderRadius: 3,
                    padding: '2px 8px',
                    border: `1px solid ${statusStyles[latest.status].color}30`,
                  }}
                >
                  {statusStyles[latest.status].label}
                </span>
                <span
                  style={{
                    fontFamily: 'var(--font-body)',
                    fontSize: 13,
                    color: 'var(--text-muted)',
                  }}
                >
                  {formatRelativeTime(latest.finished_at)}
                </span>
              </div>
            </div>

            <div className="flex flex-col items-end gap-1">
              <div
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 13,
                  color: 'var(--text)',
                }}
              >
                ${latest.total_cost_usd.toFixed(3)}
              </div>
              <div
                style={{
                  fontFamily: 'var(--font-body)',
                  fontSize: 12,
                  color: 'var(--text-muted)',
                }}
              >
                {formatDuration(latest.started_at, latest.finished_at)} · {latest.batches_total - latest.batches_failed}/{latest.batches_total} batches
              </div>
            </div>
          </div>

          {latest.note && (
            <div
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 12,
                color: 'var(--text-muted)',
                fontStyle: 'italic',
                padding: '6px 10px',
                background: 'var(--surface-2)',
                borderRadius: 'var(--radius)',
                border: '1px solid var(--border)',
              }}
            >
              {latest.note}
            </div>
          )}

          {/* Divider */}
          <div style={{ borderTop: '1px solid var(--border)' }} />

          {/* Next run */}
          <div className="flex justify-between items-center">
            <span
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 12,
                color: 'var(--text-muted)',
              }}
            >
              Next run
            </span>
            <span
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 13,
                color: schedule.cadence === 'off' ? 'var(--text-muted)' : 'var(--text)',
                fontWeight: schedule.cadence === 'off' ? 400 : 500,
              }}
            >
              {getNextRunDate(schedule)}
            </span>
          </div>

          {schedule.cadence !== 'off' && (
            <div className="flex justify-between items-center">
              <span
                style={{
                  fontFamily: 'var(--font-body)',
                  fontSize: 12,
                  color: 'var(--text-muted)',
                }}
              >
                Email
              </span>
              <span
                style={{
                  fontFamily: 'var(--font-body)',
                  fontSize: 12,
                  color: 'var(--text-muted)',
                }}
              >
                {schedule.email_mode === 'draft_only' ? 'Draft only' : 'Auto-send'}
                {' '}· {DAY_LABELS[schedule.day_of_week]}s
              </span>
            </div>
          )}
        </div>
      ) : (
        <p
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 13,
            color: 'var(--text-muted)',
          }}
        >
          No runs recorded yet.
        </p>
      )}
    </section>
  )
}
