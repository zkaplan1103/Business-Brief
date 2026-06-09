import { motion } from 'framer-motion'
import type { Brief, ThemeReport } from '../types'

interface Props {
  brief: Brief
  themeReport: ThemeReport
  onTabChange: (t: 'overview' | 'charts' | 'actions') => void
}

const glass: React.CSSProperties = {
  background: 'var(--glass-bg)',
  backdropFilter: 'blur(16px) saturate(1.6)',
  WebkitBackdropFilter: 'blur(16px) saturate(1.6)',
  border: '1px solid var(--glass-border)',
  boxShadow: 'var(--glass-shadow)',
  borderRadius: 'var(--radius)',
}

function Gauge({ score }: { score: number }) {
  const arcLen = Math.PI * 130
  const fill = (score / 5) * arcLen
  const offset = arcLen - fill

  return (
    <div style={{ position: 'relative', width: 300, height: 162 }}>
      <svg width="300" height="162" viewBox="0 0 300 162" style={{ overflow: 'visible' }}>
        <defs>
          <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="var(--brand)" stopOpacity="0.7" />
            <stop offset="100%" stopColor="var(--brand)" stopOpacity="1" />
          </linearGradient>
        </defs>
        <path d="M 20 150 A 130 130 0 0 1 280 150" fill="none" stroke="var(--surface-2)" strokeWidth="18" strokeLinecap="round"/>
        <motion.path
          d="M 20 150 A 130 130 0 0 1 280 150"
          fill="none" stroke="url(#gaugeGrad)" strokeWidth="18" strokeLinecap="round"
          strokeDasharray={arcLen}
          initial={{ strokeDashoffset: arcLen }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1.4, ease: [0.2, 0.8, 0.2, 1] }}
        />
      </svg>
      <div style={{ position: 'absolute', bottom: 0, left: '50%', transform: 'translateX(-50%)', whiteSpace: 'nowrap', textAlign: 'center' }}>
        <span style={{ fontSize: 72, fontWeight: 800, color: 'var(--ink)', lineHeight: 1, letterSpacing: '-0.04em' }}>{score.toFixed(1)}</span>
        <span style={{ fontSize: 24, fontWeight: 400, color: 'var(--ink-faint)' }}>/5</span>
      </div>
    </div>
  )
}

const ArrowRight = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M5 12h14M12 5l7 7-7 7"/>
  </svg>
)

export default function OverviewTab({ brief, themeReport, onTabChange }: Props) {
  const delta = themeReport.prev_avg_stars != null ? themeReport.avg_stars - themeReport.prev_avg_stars : null
  const isUp = brief.trend === 'up'
  const isDown = brief.trend === 'down'
  const topThemes = themeReport.themes.slice(0, 3)
  const topAction = brief.action_items[0]

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: 'easeOut' }}
      style={{ display: 'flex', flexDirection: 'column', gap: 20 }}
    >

      {/* Block 1: Gauge — floats freely, no card */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '28px 32px 8px' }}>
        <Gauge score={themeReport.avg_stars} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 16, flexWrap: 'wrap' as const, justifyContent: 'center' }}>
          {delta != null && (
            <span style={{ fontSize: 13, fontWeight: 700, padding: '4px 14px', borderRadius: 999, color: isUp ? 'var(--pos)' : isDown ? 'var(--neg)' : 'var(--ink-faint)', background: isUp ? 'var(--pos-soft)' : isDown ? 'var(--neg-soft)' : 'var(--surface-2)' }}>
              {isUp ? '▲' : isDown ? '▼' : '→'} {Math.abs(delta).toFixed(1)} vs last wk
            </span>
          )}
          <span style={{ fontSize: 14, color: 'var(--ink-soft)' }}>{themeReport.review_count} review{themeReport.review_count !== 1 ? 's' : ''}</span>
        </div>
      </div>

      {/* Block 2: This week's brief */}
      <div style={{ ...glass, padding: '28px 32px', position: 'relative', overflow: 'hidden' }}>
        <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 4, background: 'var(--brand)', borderRadius: '4px 0 0 4px' }} />
        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.16em', color: 'var(--brand)', textTransform: 'uppercase' as const, marginBottom: 12 }}>
          This Week's Brief
        </div>
        <p style={{ fontSize: 15, fontWeight: 400, color: 'var(--ink)', lineHeight: 1.75 }}>{brief.summary}</p>
        {topThemes.length > 0 && (
          <div style={{ display: 'flex', gap: 8, marginTop: 20, flexWrap: 'wrap' as const }}>
            {topThemes.map(t => {
              const color = t.sentiment === 'positive' ? 'var(--pos)' : t.sentiment === 'negative' ? 'var(--neg)' : 'var(--mix)'
              return (
                <span key={t.theme_id} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'var(--glass-bg-2, var(--surface-2))', border: '1px solid var(--glass-border)', borderRadius: 999, padding: '5px 12px', fontSize: 12, fontWeight: 600, color: 'var(--ink-soft)' }}>
                  <span style={{ width: 7, height: 7, borderRadius: '50%', background: color, flexShrink: 0, display: 'inline-block' }} />
                  {t.label} · {t.count}
                </span>
              )
            })}
          </div>
        )}
      </div>

      {/* Block 3: #1 action preview */}
      {topAction && (
        <div style={{ ...glass, padding: '24px 28px', position: 'relative', overflow: 'hidden' }}>
          <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 4, background: 'var(--neg)', borderRadius: '4px 0 0 4px' }} />
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <span style={{ background: 'var(--surface-2)', border: '1px solid var(--line)', borderRadius: 6, padding: '3px 9px', fontSize: 12, fontWeight: 600, color: 'var(--ink-faint)' }}>#{topAction.rank}</span>
            <span style={{ borderRadius: 999, padding: '3px 10px', fontSize: 11, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' as const, background: 'var(--neg-soft)', color: 'var(--neg)' }}>High Priority</span>
          </div>
          <h3 style={{ fontSize: 17, fontWeight: 700, color: 'var(--ink)', lineHeight: 1.3, marginBottom: 8 }}>{topAction.headline}</h3>
          <p style={{ fontSize: 13, color: 'var(--ink-soft)', lineHeight: 1.6, marginBottom: 16 }}>{topAction.why_it_matters}</p>
          <div style={{ display: 'flex', gap: 10, background: 'var(--surface-2)', borderRadius: 8, padding: '12px 14px', alignItems: 'flex-start', marginBottom: 18 }}>
            <span style={{ fontSize: 10, fontWeight: 800, color: 'var(--brand)', letterSpacing: '0.12em', textTransform: 'uppercase' as const, whiteSpace: 'nowrap' as const, paddingTop: 2 }}>Do this</span>
            <p style={{ fontSize: 13, color: 'var(--ink)', lineHeight: 1.55, margin: 0 }}>{topAction.recommended_action}</p>
          </div>
          <button
            onClick={() => onTabChange('actions')}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 600, color: 'var(--brand)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontFamily: 'var(--font-body)', transition: 'color 0.15s' }}
            onMouseEnter={e => (e.currentTarget.style.color = 'var(--brand-deep)')}
            onMouseLeave={e => (e.currentTarget.style.color = 'var(--brand)')}
          >
            See all {brief.action_items.length} action items <ArrowRight />
          </button>
        </div>
      )}

    </motion.div>
  )
}
