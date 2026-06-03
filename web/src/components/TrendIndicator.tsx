import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { ThemeReport, Brief } from '../types'

interface TrendIndicatorProps {
  themeReport: ThemeReport
  brief: Brief
}

function useCountUp(target: number, duration = 600) {
  const [value, setValue] = useState(0)
  const raf = useRef<number | null>(null)

  useEffect(() => {
    const start = performance.now()
    const from = 0

    function tick(now: number) {
      const elapsed = now - start
      const t = Math.min(elapsed / duration, 1)
      // easeOutExpo
      const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t)
      setValue(parseFloat((from + (target - from) * eased).toFixed(2)))
      if (t < 1) raf.current = requestAnimationFrame(tick)
    }

    raf.current = requestAnimationFrame(tick)
    return () => { if (raf.current) cancelAnimationFrame(raf.current) }
  }, [target, duration])

  return value
}

export default function TrendIndicator({ themeReport, brief }: TrendIndicatorProps) {
  const count = useCountUp(themeReport.avg_stars, 600)
  const [showArrow, setShowArrow] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setShowArrow(true), 900)
    return () => clearTimeout(t)
  }, [])

  const trendColor =
    brief.trend === 'up' ? 'var(--trend-up)' :
    brief.trend === 'down' ? 'var(--trend-down)' :
    'var(--trend-flat)'

  const arrowFrom = brief.trend === 'up' ? 12 : brief.trend === 'down' ? -12 : 0
  const arrowIcon = brief.trend === 'up' ? '↑' : brief.trend === 'down' ? '↓' : '→'
  const trendLabel = brief.trend === 'up' ? 'Improving' : brief.trend === 'down' ? 'Declining' : 'Holding steady'

  const delta = themeReport.prev_avg_stars != null
    ? themeReport.avg_stars - themeReport.prev_avg_stars
    : null

  return (
    <article
      style={{
        background: 'var(--surface)',
        borderRadius: 'var(--radius)',
        boxShadow: 'var(--shadow-card)',
        padding: '20px 24px',
      }}
      aria-label="Rating trend"
    >
      <div
        style={{
          fontFamily: 'var(--font-body)',
          fontSize: 11,
          fontWeight: 600,
          color: 'var(--text-muted)',
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          marginBottom: 12,
        }}
      >
        Avg Rating This Week
      </div>

      <div className="flex items-end gap-2">
        <span
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 48,
            fontWeight: 600,
            letterSpacing: '-0.02em',
            lineHeight: 1,
            color: trendColor,
          }}
        >
          {count.toFixed(1)}
        </span>
        <span
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 18,
            color: 'var(--text-muted)',
            lineHeight: 1,
            paddingBottom: 4,
          }}
        >
          / 5
        </span>

        <AnimatePresence>
          {showArrow && (
            <motion.span
              key="arrow"
              initial={{ opacity: 0, y: arrowFrom }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: 'easeOut' }}
              style={{
                fontFamily: 'var(--font-display)',
                fontSize: 32,
                fontWeight: 600,
                color: trendColor,
                lineHeight: 1,
                paddingBottom: 4,
              }}
              aria-label={trendLabel}
            >
              {arrowIcon}
            </motion.span>
          )}
        </AnimatePresence>
      </div>

      <div className="flex items-center gap-3 mt-3">
        {delta != null && (
          <span
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 13,
              color: trendColor,
              fontWeight: 500,
            }}
          >
            {delta > 0 ? '+' : ''}{delta.toFixed(1)} vs last week
          </span>
        )}
        <span
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 13,
            color: 'var(--text-muted)',
          }}
        >
          {trendLabel}
        </span>
      </div>

      {themeReport.prev_avg_stars != null && (
        <div
          style={{
            marginTop: 12,
            paddingTop: 12,
            borderTop: '1px solid var(--border)',
          }}
        >
          <div className="flex justify-between">
            <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--text-muted)' }}>
              Prior week
            </span>
            <span
              style={{
                fontFamily: 'var(--font-display)',
                fontSize: 18,
                fontWeight: 600,
                color: 'var(--text-muted)',
              }}
            >
              {themeReport.prev_avg_stars.toFixed(1)}
            </span>
          </div>
        </div>
      )}
    </article>
  )
}
