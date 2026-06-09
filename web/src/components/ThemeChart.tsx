import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { ThemeReport } from '../types'

interface ThemeChartProps {
  themeReport: ThemeReport
}

const sentimentColor: Record<string, string> = {
  positive: 'var(--pos)',
  negative: 'var(--neg)',
  mixed: 'var(--mix)',
}
const sentimentGlyph: Record<string, string> = {
  positive: '+',
  negative: '−',
  mixed: '~',
}
const sentimentLabel: Record<string, string> = {
  positive: 'Positive',
  negative: 'Negative',
  mixed: 'Mixed',
}
const sentimentRank: Record<string, number> = {
  negative: 0, mixed: 1, positive: 2,
}

type SortMode = 'mentions' | 'sentiment'
type ViewMode = 'themes' | 'stars'

// Approximate star distribution from avg_stars + review_count for the mini star view
function buildStarDist(avg: number, total: number) {
  const fiveStarShare = Math.max(0, (avg - 3) / 2)
  const oneStarShare = Math.max(0, (4 - avg) / 3) * 0.3
  const twoStarShare = Math.max(0, (4 - avg) / 3) * 0.5
  const threeStarShare = 0.15
  const fourStarShare = 1 - fiveStarShare - oneStarShare - twoStarShare - threeStarShare
  return [5, 4, 3, 2, 1].map(s => {
    const share = s === 5 ? fiveStarShare : s === 4 ? Math.max(0, fourStarShare) : s === 3 ? threeStarShare : s === 2 ? twoStarShare : oneStarShare
    return { stars: s, count: Math.round(share * total) }
  })
}

export default function ThemeChart({ themeReport }: ThemeChartProps) {
  const [sortMode, setSortMode] = useState<SortMode>('mentions')
  const [viewMode, setViewMode] = useState<ViewMode>('themes')
  const [activeIdx, setActiveIdx] = useState<number | null>(null)

  const themes = themeReport.themes
  const maxCount = Math.max(...themes.map(t => t.count), 1)

  // Sort themes
  const sortedThemes = [...themes].sort((a, b) => {
    if (sortMode === 'mentions') return b.count - a.count
    return (sentimentRank[a.sentiment] - sentimentRank[b.sentiment]) || (b.count - a.count)
  })

  // Star distribution for "Stars" view
  const starDist = buildStarDist(themeReport.avg_stars, themeReport.review_count)
  const maxStarCount = Math.max(...starDist.map(d => d.count), 1)

  const presentSentiments = [...new Set(themes.map(t => t.sentiment))]

  function toggleDrill(idx: number) {
    setActiveIdx(prev => prev === idx ? null : idx)
  }

  const activeTheme = activeIdx !== null ? sortedThemes[activeIdx] : null

  return (
    <section
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--line)',
        borderRadius: 'var(--radius)',
        boxShadow: 'var(--shadow)',
        marginBottom: 0,
      }}
    >
      {/* Card header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          padding: '20px 22px 0',
        }}
      >
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 19, fontWeight: 600 }}>
            Themes this week
          </h2>
          <div style={{ fontSize: 12, color: 'var(--ink-faint)', marginTop: 3 }}>
            {themeReport.review_count} reviews · {viewMode === 'themes' ? 'click any bar for quotes' : 'distribution of star ratings'}
          </div>
        </div>

        {/* Toggle pills */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {/* Sort */}
          {viewMode === 'themes' && (
            <div
              style={{
                display: 'inline-flex',
                background: 'var(--surface-2)',
                border: '1px solid var(--line)',
                borderRadius: 999,
                padding: 3,
                gap: 0,
              }}
            >
              {(['mentions', 'sentiment'] as SortMode[]).map(mode => (
                <button
                  key={mode}
                  onClick={() => setSortMode(mode)}
                  style={{
                    fontFamily: 'var(--font-body)',
                    fontSize: 12,
                    fontWeight: 600,
                    color: sortMode === mode ? 'var(--ink)' : 'var(--ink-soft)',
                    background: sortMode === mode ? 'var(--surface)' : 'transparent',
                    border: 0,
                    padding: '5px 12px',
                    borderRadius: 999,
                    cursor: 'pointer',
                    boxShadow: sortMode === mode ? '0 1px 2px rgba(0,0,0,.06)' : 'none',
                    transition: 'all .15s',
                  }}
                >
                  {mode === 'mentions' ? 'Mentions' : 'Sentiment'}
                </button>
              ))}
            </div>
          )}
          {/* View */}
          <div
            style={{
              display: 'inline-flex',
              background: 'var(--surface-2)',
              border: '1px solid var(--line)',
              borderRadius: 999,
              padding: 3,
            }}
          >
            {(['themes', 'stars'] as ViewMode[]).map(mode => (
              <button
                key={mode}
                onClick={() => { setViewMode(mode); setActiveIdx(null) }}
                style={{
                  fontFamily: 'var(--font-body)',
                  fontSize: 12,
                  fontWeight: 600,
                  color: viewMode === mode ? 'var(--ink)' : 'var(--ink-soft)',
                  background: viewMode === mode ? 'var(--surface)' : 'transparent',
                  border: 0,
                  padding: '5px 12px',
                  borderRadius: 999,
                  cursor: 'pointer',
                  boxShadow: viewMode === mode ? '0 1px 2px rgba(0,0,0,.06)' : 'none',
                  transition: 'all .15s',
                }}
              >
                {mode === 'themes' ? 'Themes' : 'Stars'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Legend — only for themes view */}
      {viewMode === 'themes' && (
        <div style={{ display: 'flex', gap: 16, padding: '14px 22px 4px', flexWrap: 'wrap' as const }}>
          {presentSentiments.map(s => (
            <span key={s} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--ink-soft)', fontWeight: 500 }}>
              <span
                style={{
                  width: 16, height: 16, borderRadius: 5,
                  background: sentimentColor[s],
                  display: 'grid', placeItems: 'center',
                  fontSize: 10, color: '#fff', fontWeight: 800,
                }}
              >
                {sentimentGlyph[s]}
              </span>
              {sentimentLabel[s]}
            </span>
          ))}
        </div>
      )}

      {/* Horizontal bar chart */}
      <div style={{ padding: '8px 22px 4px' }}>
        {viewMode === 'themes'
          ? sortedThemes.map((theme, i) => {
              const fillPct = (theme.count / maxCount) * 100
              const isActive = activeIdx === i
              return (
                <div
                  key={theme.theme_id}
                  onClick={() => toggleDrill(i)}
                  tabIndex={0}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleDrill(i) } }}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'minmax(140px, 28%) 1fr 34px',
                    alignItems: 'center',
                    gap: 12,
                    padding: '7px 0',
                    cursor: 'pointer',
                    borderRadius: 8,
                    background: isActive ? 'var(--surface-2)' : 'transparent',
                    transition: 'background .15s',
                    paddingLeft: isActive ? 6 : 0,
                    paddingRight: isActive ? 6 : 0,
                  }}
                  role="button"
                  aria-expanded={isActive}
                >
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 600,
                      color: isActive ? 'var(--brand)' : 'var(--ink)',
                      textAlign: 'right' as const,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      justifyContent: 'flex-end',
                    }}
                  >
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 800,
                        color: sentimentColor[theme.sentiment],
                      }}
                    >
                      {sentimentGlyph[theme.sentiment]}
                    </span>
                    <span style={{ textAlign: 'right' as const, lineHeight: 1.25, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' as const, overflow: 'hidden' }}>
                      {theme.label}
                    </span>
                  </div>

                  <div
                    style={{
                      height: 22,
                      background: 'var(--surface-2)',
                      borderRadius: 6,
                      overflow: 'hidden',
                      position: 'relative' as const,
                    }}
                  >
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${fillPct}%` }}
                      transition={{ duration: 0.8, ease: [0.2, 0.8, 0.2, 1] }}
                      style={{
                        height: '100%',
                        background: sentimentColor[theme.sentiment],
                        borderRadius: 6,
                        opacity: 0.85,
                      }}
                    />
                  </div>

                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--ink-soft)', textAlign: 'left' as const }}>
                    {theme.count}
                  </div>
                </div>
              )
            })
          : starDist.map(({ stars, count }) => {
              const fillPct = (count / maxStarCount) * 100
              const sent = stars >= 4 ? 'positive' : stars === 3 ? 'mixed' : 'negative'
              return (
                <div
                  key={stars}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '60px 1fr 34px',
                    alignItems: 'center',
                    gap: 12,
                    padding: '7px 0',
                  }}
                >
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)', textAlign: 'right' as const }}>
                    {stars} ★
                  </div>
                  <div style={{ height: 22, background: 'var(--surface-2)', borderRadius: 6, overflow: 'hidden' }}>
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${fillPct}%` }}
                      transition={{ duration: 0.7, ease: [0.2, 0.8, 0.2, 1] }}
                      style={{ height: '100%', background: sentimentColor[sent], borderRadius: 6, opacity: 0.8 }}
                    />
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--ink-soft)' }}>{count}</div>
                </div>
              )
            })
        }
      </div>

      {/* Drill-down quote panel */}
      <AnimatePresence>
        {activeTheme && (
          <motion.div
            key={activeTheme.theme_id}
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.28, ease: 'easeOut' }}
            style={{ overflow: 'hidden' }}
          >
            <div
              style={{
                margin: '6px 22px 18px',
                border: '1px solid var(--line)',
                borderLeft: '3px solid var(--brand)',
                borderRadius: 10,
                background: 'var(--surface-2)',
                padding: '16px 18px',
              }}
            >
              <h4 style={{ fontFamily: 'var(--font-display)', fontSize: 15, marginBottom: 4 }}>
                {activeTheme.label}
              </h4>
              <div style={{ fontSize: 12, color: 'var(--ink-faint)', marginBottom: 12 }}>
                {activeTheme.count} mention{activeTheme.count !== 1 ? 's' : ''} · {sentimentLabel[activeTheme.sentiment]} sentiment
              </div>
              {activeTheme.sample_quotes.map((q, i) => (
                <div
                  key={i}
                  style={{
                    fontFamily: 'var(--font-display)',
                    fontStyle: 'italic',
                    fontSize: 14,
                    color: 'var(--ink)',
                    padding: '8px 0 8px 14px',
                    borderLeft: '2px solid var(--line-strong)',
                    marginBottom: i < activeTheme.sample_quotes.length - 1 ? 8 : 0,
                    lineHeight: 1.5,
                  }}
                >
                  "{q}"
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}
