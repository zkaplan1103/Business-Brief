import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { ThemeReport, Brief } from '../types'

interface TrendIndicatorProps {
  themeReport: ThemeReport
  brief: Brief
}

function useCountUp(target: number, duration = 550) {
  const [value, setValue] = useState(0)
  const raf = useRef<number | null>(null)

  useEffect(() => {
    const start = performance.now()
    function tick(now: number) {
      const t = Math.min((now - start) / duration, 1)
      const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t)
      setValue(parseFloat((target * eased).toFixed(2)))
      if (t < 1) raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => { if (raf.current) cancelAnimationFrame(raf.current) }
  }, [target, duration])

  return value
}

export default function TrendIndicator({ themeReport, brief }: TrendIndicatorProps) {
  const count = useCountUp(themeReport.avg_stars)
  const [showArrow, setShowArrow] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setShowArrow(true), 700)
    return () => clearTimeout(t)
  }, [])

  const trendColor =
    brief.trend === 'up' ? 'var(--trend-up)' :
    brief.trend === 'down' ? 'var(--trend-down)' :
    'var(--trend-flat)'

  const arrowIcon = brief.trend === 'up' ? '↑' : brief.trend === 'down' ? '↓' : '→'
  const arrowFrom = brief.trend === 'up' ? 8 : brief.trend === 'down' ? -8 : 0

  const delta = themeReport.prev_avg_stars != null
    ? themeReport.avg_stars - themeReport.prev_avg_stars
    : null

  return (
    <article
      style={{
        background: 'var(--surface)',
        borderRadius: 'var(--radius)',
        boxShadow: 'var(--shadow-card)',
        padding: '16px 20px',
        border: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        gap: 16,
      }}
      aria-label="Rating trend"
    >
      {/* Big number */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, flexShrink: 0 }}>
        <span
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 44,
            fontWeight: 600,
            letterSpacing: '-0.03em',
            lineHeight: 1,
            color: trendColor,
          }}
        >
          {count.toFixed(1)}
        </span>
        <span
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 14,
            color: 'var(--text-muted)',
            paddingBottom: 4,
          }}
        >
          /5
        </span>
        <AnimatePresence>
          {showArrow && (
            <motion.span
              key="arrow"
              initial={{ opacity: 0, y: arrowFrom }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              style={{
                fontFamily: 'var(--font-display)',
                fontSize: 28,
                color: trendColor,
                lineHeight: 1,
                paddingBottom: 4,
                marginLeft: 2,
              }}
              aria-label={brief.trend}
            >
              {arrowIcon}
            </motion.span>
          )}
        </AnimatePresence>
      </div>

      {/* Divider + detail */}
      <div
        style={{
          borderLeft: '1px solid var(--border)',
          paddingLeft: 16,
          flex: 1,
          minWidth: 0,
        }}
      >
        <div
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 13,
            fontWeight: 500,
            color: trendColor,
            marginBottom: 2,
          }}
        >
          {delta != null ? (
            <>{delta > 0 ? '+' : ''}{delta.toFixed(1)} vs last week</>
          ) : (
            <>No prior week</>
          )}
        </div>
        {themeReport.prev_avg_stars != null && (
          <div
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 12,
              color: 'var(--text-muted)',
            }}
          >
            Was {themeReport.prev_avg_stars.toFixed(1)} last week
          </div>
        )}
        <div
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 12,
            color: 'var(--text-muted)',
            marginTop: 2,
          }}
        >
          {themeReport.review_count} review{themeReport.review_count !== 1 ? 's' : ''}
        </div>
      </div>
    </article>
  )
}
