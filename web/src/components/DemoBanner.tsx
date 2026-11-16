import type { BusinessMeta } from '../types'

// Shown only in the static demo build (VITE_DEMO=1). Settings are hidden there,
// so the business and week pickers live here instead.

interface Props {
  businesses: BusinessMeta[]
  selectedBusiness: string
  onBusinessChange: (id: string) => void
  weeks: string[]
  selectedWeek: string
  onWeekChange: (w: string) => void
}

const selectStyle: React.CSSProperties = {
  background: 'var(--surface)', border: '1px solid var(--line-strong)', borderRadius: 8,
  padding: '6px 8px', fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500,
  color: 'var(--ink)', cursor: 'pointer', minWidth: 0, flex: '1 1 160px',
}

export default function DemoBanner({
  businesses, selectedBusiness, onBusinessChange, weeks, selectedWeek, onWeekChange,
}: Props) {
  return (
    <div style={{ background: 'var(--surface-2)', borderBottom: '1px solid var(--line)' }}>
      <div style={{ maxWidth: 1180, margin: '0 auto', padding: '10px 16px', display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px 16px' }}>
        <p style={{ fontSize: 13, color: 'var(--ink-soft)', margin: 0, flex: '1 1 280px' }}>
          Demo with simulated data. See{' '}
          <a href="https://github.com/zkaplan1103/Business-Brief" style={{ color: 'var(--brand)', fontWeight: 600 }}>GitHub</a>
          {' '}for the AWS pipeline.
        </p>
        <div style={{ display: 'flex', gap: 8, flex: '1 1 320px', maxWidth: 460 }}>
          <select aria-label="Business" style={selectStyle} value={selectedBusiness} onChange={e => onBusinessChange(e.target.value)}>
            {businesses.map(b => <option key={b.business_id} value={b.business_id}>{b.business_name}</option>)}
          </select>
          <select aria-label="Week" style={selectStyle} value={selectedWeek} onChange={e => onWeekChange(e.target.value)}>
            {weeks.map(w => <option key={w} value={w}>{`Week ${w.split('-W')[1]}, ${w.split('-W')[0]}`}</option>)}
          </select>
        </div>
      </div>
    </div>
  )
}
