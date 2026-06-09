import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { ThemeReport } from '../types'

interface Props { themeReport: ThemeReport }

type SortMode = 'mentions' | 'sentiment'
type ViewMode = 'themes' | 'stars'

const sentimentColor: Record<string, string> = { positive: 'var(--pos)', negative: 'var(--neg)', mixed: 'var(--mix)' }
const sentimentFill: Record<string, string> = { positive: 'rgba(22,101,52,0.75)', negative: 'rgba(159,18,57,0.75)', mixed: 'rgba(75,85,99,0.55)' }
const sentimentGlyph: Record<string, string> = { positive: '+', negative: '−', mixed: '~' }
const sentimentRank: Record<string, number> = { negative: 0, mixed: 1, positive: 2 }
const STAR_COLORS: Record<number, string> = { 5: '#166534', 4: '#22C55E', 3: '#4B5563', 2: '#F97316', 1: '#9F1239' }

function ToggleGroup({ options, active, onSelect }: { options: { id: string; label: string }[]; active: string; onSelect: (id: string) => void }) {
  return (
    <div style={{ display: 'inline-flex', background: 'var(--surface-2)', border: '1px solid var(--line)', borderRadius: 999, padding: 3 }}>
      {options.map(o => (
        <button key={o.id} onClick={() => onSelect(o.id)} style={{ fontFamily: 'var(--font-body)', fontSize: 12, fontWeight: 600, color: active === o.id ? 'var(--ink)' : 'var(--ink-soft)', background: active === o.id ? 'var(--surface)' : 'transparent', border: 0, padding: '5px 13px', borderRadius: 999, cursor: 'pointer', boxShadow: active === o.id ? '0 1px 2px rgba(0,0,0,.06)' : 'none', transition: 'all .15s' }}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

export default function ChartsTab({ themeReport }: Props) {
  const [sortMode, setSortMode] = useState<SortMode>('mentions')
  const [viewMode, setViewMode] = useState<ViewMode>('themes')
  const [activeDrill, setActiveDrill] = useState<string | null>(null)

  const themes = [...themeReport.themes].sort((a, b) =>
    sortMode === 'mentions' ? b.count - a.count : (sentimentRank[a.sentiment] - sentimentRank[b.sentiment]) || (b.count - a.count)
  )
  const maxCount = Math.max(...themes.map(t => t.count), 1)

  // star distribution
  const avg = themeReport.avg_stars; const total = themeReport.review_count
  const fiveFrac = Math.max(0, (avg - 3) / 2)
  const oneFrac = Math.max(0, (4 - avg) / 3) * 0.3
  const twoFrac = Math.max(0, (4 - avg) / 3) * 0.5
  const threeFrac = 0.15
  const fourFrac = Math.max(0, 1 - fiveFrac - oneFrac - twoFrac - threeFrac)
  const starCounts: Record<number, number> = { 5: Math.round(fiveFrac * total), 4: Math.round(fourFrac * total), 3: Math.round(threeFrac * total), 2: Math.round(twoFrac * total), 1: Math.round(oneFrac * total) }
  const maxStar = Math.max(...Object.values(starCounts), 1)

  // sentiment totals for donut — use total mentions as denominator (one review may mention multiple themes)
  const totalMentions = themes.reduce((s, t) => s + t.count, 0) || 1
  const posPct = Math.round((themes.filter(t => t.sentiment === 'positive').reduce((s, t) => s + t.count, 0) / totalMentions) * 100)
  const negPct = Math.round((themes.filter(t => t.sentiment === 'negative').reduce((s, t) => s + t.count, 0) / totalMentions) * 100)
  const mixPct = 100 - posPct - negPct

  const card: React.CSSProperties = { background: 'var(--glass-bg)', backdropFilter: 'blur(16px) saturate(1.6)', WebkitBackdropFilter: 'blur(16px) saturate(1.6)', border: '1px solid var(--glass-border)', boxShadow: 'var(--glass-shadow)', borderRadius: 'var(--radius)', padding: '22px 24px', marginBottom: 20 }

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, ease: 'easeOut' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 22, gap: 16 }}>
        <div>
          <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)' }}>Theme Analysis</div>
          <div style={{ fontSize: 13, color: 'var(--ink-soft)', marginTop: 3 }}>{themeReport.review_count} reviews · click any bar for quotes</div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0, alignItems: 'center' }}>
          <div style={{ transition: 'opacity 0.15s', opacity: viewMode === 'themes' ? 1 : 0, pointerEvents: viewMode === 'themes' ? 'auto' : 'none' }}>
            <ToggleGroup options={[{ id: 'mentions', label: 'Mentions' }, { id: 'sentiment', label: 'Sentiment' }]} active={sortMode} onSelect={v => setSortMode(v as SortMode)} />
          </div>
          <ToggleGroup options={[{ id: 'themes', label: 'Themes' }, { id: 'stars', label: 'Stars' }]} active={viewMode} onSelect={v => { setViewMode(v as ViewMode); setActiveDrill(null) }} />
        </div>
      </div>

      {/* Main chart card */}
      <div style={card}>
        {/* Legend */}
        {viewMode === 'themes' && (
          <div style={{ display: 'flex', gap: 16, marginBottom: 16, flexWrap: 'wrap' as const }}>
            {['positive', 'mixed', 'negative'].map(s => (
              <span key={s} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 500, color: 'var(--ink-soft)' }}>
                <span style={{ width: 10, height: 10, borderRadius: 3, background: sentimentColor[s], display: 'inline-block' }} />
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </span>
            ))}
          </div>
        )}

        {viewMode === 'themes' ? themes.map(theme => {
          const isActive = activeDrill === theme.theme_id
          return (
            <div key={theme.theme_id}>
              <div
                onClick={() => setActiveDrill(isActive ? null : theme.theme_id)}
                style={{ display: 'grid', gridTemplateColumns: '200px 1fr 36px', alignItems: 'center', gap: 14, padding: '8px 6px', borderRadius: 7, cursor: 'pointer', background: isActive ? 'var(--surface-2)' : 'transparent', transition: 'background 0.1s' }}
                role="button" tabIndex={0}
                onKeyDown={e => { if (e.key === 'Enter') setActiveDrill(isActive ? null : theme.theme_id) }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 6, textAlign: 'right' as const }}>
                  <span style={{ fontSize: 10, fontWeight: 800, color: sentimentColor[theme.sentiment] }}>{sentimentGlyph[theme.sentiment]}</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: isActive ? 'var(--brand)' : 'var(--ink)', lineHeight: 1.3, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' as const, overflow: 'hidden', textAlign: 'right' as const }}>{theme.label}</span>
                </div>
                <div style={{ height: 24, background: 'var(--surface-2)', borderRadius: 6, overflow: 'hidden' }}>
                  <motion.div initial={{ width: 0 }} animate={{ width: `${(theme.count / maxCount) * 100}%` }} transition={{ duration: 0.8, ease: [0.2, 0.8, 0.2, 1] }}
                    style={{ height: '100%', borderRadius: 6, background: sentimentFill[theme.sentiment] }} />
                </div>
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--ink-soft)', textAlign: 'right' as const }}>{theme.count}</div>
              </div>

              <AnimatePresence>
                {isActive && theme.sample_quotes.length > 0 && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.25, ease: 'easeOut' }} style={{ overflow: 'hidden' }}>
                    <div style={{ margin: '4px 0 8px', background: 'var(--surface-2)', border: '1px solid var(--line)', borderLeft: '3px solid var(--brand)', borderRadius: 10, padding: '14px 16px' }}>
                      <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)', marginBottom: 3 }}>{theme.label}</div>
                      <div style={{ fontSize: 12, color: 'var(--ink-faint)', marginBottom: 10 }}>{theme.count} mention{theme.count !== 1 ? 's' : ''} · {theme.sentiment} sentiment</div>
                      {theme.sample_quotes.map((q, i) => (
                        <div key={i} style={{ fontSize: 13, fontStyle: 'italic', color: 'var(--ink)', padding: '7px 0 7px 14px', borderLeft: '2px solid var(--line-strong)', lineHeight: 1.5, marginBottom: i < theme.sample_quotes.length - 1 ? 7 : 0 }}>"{q}"</div>
                      ))}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )
        }) : [5,4,3,2,1].map(star => (
          <div key={star} style={{ display: 'grid', gridTemplateColumns: '60px 1fr 36px', alignItems: 'center', gap: 14, padding: '8px 0' }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)', textAlign: 'right' as const }}>{star} ★</div>
            <div style={{ height: 24, background: 'var(--surface-2)', borderRadius: 6, overflow: 'hidden' }}>
              <motion.div initial={{ width: 0 }} animate={{ width: `${(starCounts[star] / maxStar) * 100}%` }} transition={{ duration: 0.8, ease: [0.2, 0.8, 0.2, 1] }}
                style={{ height: '100%', borderRadius: 6, background: STAR_COLORS[star], opacity: 0.8 }} />
            </div>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--ink-soft)', textAlign: 'right' as const }}>{starCounts[star]}</div>
          </div>
        ))}
      </div>

      {/* 2-col: sentiment donut + rating trend */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>

        {/* Sentiment breakdown */}
        <div style={{ ...card, marginBottom: 0 }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--ink)', marginBottom: 3 }}>Sentiment breakdown</div>
          <div style={{ fontSize: 12, color: 'var(--ink-faint)', marginBottom: 18 }}>Share of reviews by tone</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
            <svg width="90" height="90" viewBox="0 0 90 90" style={{ flexShrink: 0 }}>
              <circle cx="45" cy="45" r="32" fill="none" stroke="var(--surface-2)" strokeWidth="12"/>
              <circle cx="45" cy="45" r="32" fill="none" stroke="var(--pos)" strokeWidth="12"
                strokeDasharray={`${(posPct / 100) * 201.1} 201.1`} strokeDashoffset="50" strokeLinecap="butt"/>
              <circle cx="45" cy="45" r="32" fill="none" stroke="var(--mix)" strokeWidth="12"
                strokeDasharray={`${(mixPct / 100) * 201.1} 201.1`} strokeDashoffset={`${-(posPct / 100) * 201.1 + 50}`} strokeLinecap="butt"/>
              <circle cx="45" cy="45" r="32" fill="none" stroke="var(--neg)" strokeWidth="12"
                strokeDasharray={`${(negPct / 100) * 201.1} 201.1`} strokeDashoffset={`${-((posPct + mixPct) / 100) * 201.1 + 50}`} strokeLinecap="butt"/>
              <text x="45" y="50" fontSize="13" fontWeight="700" fill="var(--ink)" fontFamily="'Plus Jakarta Sans',sans-serif" textAnchor="middle">{posPct}%</text>
            </svg>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[{ label: 'Positive', pct: posPct, color: 'var(--pos)' }, { label: 'Mixed', pct: mixPct, color: 'var(--mix)' }, { label: 'Negative', pct: negPct, color: 'var(--neg)' }].map(row => (
                <div key={row.label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ width: 10, height: 10, borderRadius: 3, background: row.color, flexShrink: 0, display: 'inline-block' }} />
                  <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink-soft)', width: 60 }}>{row.label}</span>
                  <div style={{ flex: 1, height: 5, background: 'var(--surface-2)', borderRadius: 999, overflow: 'hidden' }}>
                    <div style={{ height: '100%', borderRadius: 999, background: row.color, width: `${row.pct}%` }} />
                  </div>
                  <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--ink-soft)', width: 30, textAlign: 'right' as const }}>{row.pct}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Rating trend placeholder */}
        <div style={{ ...card, marginBottom: 0 }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--ink)', marginBottom: 3 }}>Rating trend</div>
          <div style={{ fontSize: 12, color: 'var(--ink-faint)', marginBottom: 16 }}>Avg stars · this week</div>
          <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'center', height: 80, gap: 0 }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 48, background: 'var(--brand)', borderRadius: '6px 6px 0 0', opacity: 0.85, height: `${(themeReport.avg_stars / 5) * 72}px`, minHeight: 8 }} />
              <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--brand)' }}>{themeReport.avg_stars.toFixed(1)} ★</span>
            </div>
          </div>
          <p style={{ fontSize: 12, color: 'var(--ink-faint)', marginTop: 12, fontStyle: 'italic' }}>Multi-week trend available once more weeks are collected.</p>
        </div>

      </div>
    </motion.div>
  )
}
