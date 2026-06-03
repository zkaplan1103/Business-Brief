import type { BusinessMeta, Brief, ThemeReport } from '../types'

interface HeaderProps {
  business: BusinessMeta
  brief: Brief
  themeReport: ThemeReport
  selectedWeek: string
  onWeekChange: (week: string) => void
}

export default function Header({ business, brief, themeReport, selectedWeek, onWeekChange }: HeaderProps) {
  const delta = themeReport.prev_avg_stars != null
    ? (themeReport.avg_stars - themeReport.prev_avg_stars).toFixed(1)
    : null

  const trendColor =
    brief.trend === 'up' ? 'var(--trend-up)' :
    brief.trend === 'down' ? 'var(--trend-down)' :
    'var(--trend-flat)'

  const trendArrow =
    brief.trend === 'up' ? '↑' :
    brief.trend === 'down' ? '↓' :
    '→'

  const deltaLabel = delta != null
    ? `${Number(delta) > 0 ? '+' : ''}${delta} from last week`
    : 'No prior week'

  function formatWeek(w: string) {
    // "2024-W31" → "Week 31, 2024"
    const [year, wk] = w.split('-W')
    return `Week ${wk}, ${year}`
  }

  return (
    <header
      style={{
        background: 'var(--surface)',
        boxShadow: 'var(--shadow-card)',
        borderBottom: '1px solid var(--border)',
      }}
    >
      <div
        style={{ maxWidth: 1200, margin: '0 auto', padding: '20px 24px' }}
        className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
      >
        {/* Left: business name + week */}
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-3 flex-wrap">
            <h1
              style={{
                fontFamily: 'var(--font-display)',
                fontSize: 32,
                fontWeight: 600,
                letterSpacing: '-0.02em',
                lineHeight: 1.1,
                color: 'var(--text)',
              }}
            >
              {business.business_name}
            </h1>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: 'var(--text-muted)',
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
                padding: '2px 8px',
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
              }}
            >
              {brief.generated_by}
            </span>
          </div>

          {/* Week selector */}
          <div className="flex items-center gap-2">
            <label
              htmlFor="week-select"
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 13,
                color: 'var(--text-muted)',
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
                fontWeight: 500,
              }}
            >
              Brief for
            </label>
            <select
              id="week-select"
              value={selectedWeek}
              onChange={e => onWeekChange(e.target.value)}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 13,
                color: 'var(--text)',
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
                padding: '4px 10px',
                outline: 'none',
                cursor: 'pointer',
              }}
              onFocus={e => { e.currentTarget.style.boxShadow = '0 0 0 3px var(--focus-ring)' }}
              onBlur={e => { e.currentTarget.style.boxShadow = 'none' }}
            >
              {business.weeks.map(w => (
                <option key={w} value={w}>{formatWeek(w)}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Right: headline verdict */}
        <div
          className="flex flex-col items-start sm:items-end gap-0"
          aria-label="Rating summary"
        >
          <div className="flex items-baseline gap-3">
            <span
              style={{
                fontFamily: 'var(--font-display)',
                fontSize: 64,
                fontWeight: 600,
                letterSpacing: '-0.02em',
                lineHeight: 1,
                color: trendColor,
              }}
              aria-label={`${themeReport.avg_stars} stars`}
            >
              {themeReport.avg_stars.toFixed(1)}
            </span>
            <span
              style={{
                fontFamily: 'var(--font-display)',
                fontSize: 32,
                fontWeight: 400,
                color: 'var(--text-muted)',
                lineHeight: 1,
                marginBottom: 4,
              }}
            >
              / 5
            </span>
            <span
              style={{
                fontFamily: 'var(--font-display)',
                fontSize: 48,
                fontWeight: 600,
                color: trendColor,
                lineHeight: 1,
              }}
              aria-label={`Trend: ${brief.trend}`}
            >
              {trendArrow}
            </span>
          </div>
          <div
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 13,
              color: trendColor,
              fontWeight: 500,
              letterSpacing: '0.01em',
            }}
          >
            {trendArrow} {deltaLabel}
          </div>
          <div
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 13,
              color: 'var(--text-muted)',
              marginTop: 2,
            }}
          >
            {themeReport.review_count} reviews this week
          </div>
        </div>
      </div>
    </header>
  )
}
