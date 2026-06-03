import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { Brief, ThemeReport, ActionItem } from '../types'

interface BriefPanelProps {
  brief: Brief
  themeReport: ThemeReport
}

const severityStyles: Record<string, { color: string; bg: string; label: string }> = {
  high: { color: 'var(--sev-high)', bg: 'color-mix(in srgb, var(--sev-high) 8%, var(--surface))', label: 'High Priority' },
  medium: { color: 'var(--sev-medium)', bg: 'color-mix(in srgb, var(--sev-medium) 8%, var(--surface))', label: 'Medium Priority' },
  low: { color: 'var(--sev-low)', bg: 'color-mix(in srgb, var(--sev-low) 8%, var(--surface))', label: 'Low Priority' },
}

interface EvidenceDrawerProps {
  item: ActionItem
  themeReport: ThemeReport
  open: boolean
}

function EvidenceDrawer({ item, themeReport, open }: EvidenceDrawerProps) {
  const theme = themeReport.themes.find(t => t.theme_id === item.theme_id)
  if (!theme) return null

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="drawer"
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
          style={{ overflow: 'hidden' }}
        >
          <div
            style={{
              marginTop: 16,
              paddingTop: 16,
              borderTop: '1px solid var(--border)',
            }}
          >
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
              Evidence — {item.evidence_review_ids.length} review{item.evidence_review_ids.length !== 1 ? 's' : ''}
            </div>
            <div className="flex flex-col gap-3">
              {theme.sample_quotes.map((quote, i) => (
                <blockquote
                  key={i}
                  style={{
                    margin: 0,
                    paddingLeft: 12,
                    borderLeft: '2px solid var(--border)',
                    fontFamily: 'var(--font-display)',
                    fontStyle: 'italic',
                    fontSize: 15,
                    color: 'var(--text-muted)',
                    lineHeight: 1.55,
                  }}
                >
                  "{quote}"
                </blockquote>
              ))}
            </div>
            <div
              style={{
                marginTop: 10,
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: 'var(--text-muted)',
              }}
            >
              Review IDs: {item.evidence_review_ids.join(', ')}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

interface ActionCardProps {
  item: ActionItem
  themeReport: ThemeReport
  index: number
  isFirst: boolean
}

function ActionCard({ item, themeReport, index, isFirst }: ActionCardProps) {
  const [evidenceOpen, setEvidenceOpen] = useState(false)
  const sev = severityStyles[item.severity]

  return (
    <motion.article
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: 'easeOut', delay: index * 0.07 }}
      whileHover={{ y: -2, boxShadow: '0 4px 16px rgba(28,22,18,0.10), 0 0 0 1px var(--border)' }}
      style={{
        background: 'var(--surface)',
        borderRadius: 'var(--radius)',
        boxShadow: 'var(--shadow-card)',
        padding: isFirst ? '24px 28px' : '18px 24px',
        cursor: 'pointer',
        transition: 'box-shadow 0.15s easeOut',
        border: isFirst ? `1.5px solid ${sev.color}` : '1px solid var(--border)',
        position: 'relative',
      }}
      onClick={() => setEvidenceOpen(v => !v)}
      role="button"
      aria-expanded={evidenceOpen}
      aria-label={`Action item: ${item.headline}`}
      tabIndex={0}
      className="focus-card"
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setEvidenceOpen(v => !v) } }}
    >
      {/* Rank badge — absolutely positioned on first card */}
      {isFirst && (
        <div
          style={{
            position: 'absolute',
            top: -1,
            right: 16,
            background: sev.color,
            color: '#fff',
            fontFamily: 'var(--font-body)',
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            padding: '2px 10px',
            borderRadius: '0 0 4px 4px',
          }}
        >
          #1 Priority
        </div>
      )}

      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          {/* Severity tag */}
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 5,
                fontFamily: 'var(--font-body)',
                fontSize: 11,
                fontWeight: 600,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                color: sev.color,
                background: sev.bg,
                borderRadius: 3,
                padding: '2px 8px',
                border: `1px solid ${sev.color}30`,
              }}
            >
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: sev.color,
                  display: 'inline-block',
                }}
              />
              {sev.label}
            </span>
            {!isFirst && (
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  color: 'var(--text-muted)',
                }}
              >
                #{item.rank}
              </span>
            )}
          </div>

          {/* Headline */}
          <h3
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: isFirst ? 24 : 18,
              fontWeight: 600,
              color: 'var(--text)',
              letterSpacing: '-0.02em',
              lineHeight: 1.2,
              marginBottom: 8,
            }}
          >
            {item.headline}
          </h3>

          {/* Why it matters */}
          <p
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: isFirst ? 15 : 13,
              color: 'var(--text-muted)',
              lineHeight: 1.55,
              marginBottom: 10,
            }}
          >
            {item.why_it_matters}
          </p>

          {/* Recommended action */}
          <div
            style={{
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius)',
              padding: '10px 14px',
              display: 'flex',
              gap: 10,
              alignItems: 'flex-start',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 11,
                fontWeight: 600,
                color: 'var(--accent-1)',
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                marginTop: 1,
                flexShrink: 0,
              }}
            >
              Do this
            </span>
            <p
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 13,
                color: 'var(--text)',
                lineHeight: 1.55,
                margin: 0,
              }}
            >
              {item.recommended_action}
            </p>
          </div>
        </div>

        {/* Evidence toggle chevron */}
        <button
          onClick={e => { e.stopPropagation(); setEvidenceOpen(v => !v) }}
          style={{
            flexShrink: 0,
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: 4,
            color: 'var(--text-muted)',
            fontSize: 18,
            lineHeight: 1,
            transform: evidenceOpen ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform 0.2s ease',
            marginTop: 2,
          }}
          aria-label={evidenceOpen ? 'Hide evidence' : 'Show evidence'}
        >
          ⌄
        </button>
      </div>

      <EvidenceDrawer item={item} themeReport={themeReport} open={evidenceOpen} />
    </motion.article>
  )
}

export default function BriefPanel({ brief, themeReport }: BriefPanelProps) {
  return (
    <section aria-label="Action brief">
      {/* Summary */}
      <div
        style={{
          background: 'var(--surface)',
          borderRadius: 'var(--radius)',
          boxShadow: 'var(--shadow-card)',
          padding: '20px 24px',
          marginBottom: 16,
        }}
      >
        <div
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 11,
            fontWeight: 600,
            color: 'var(--text-muted)',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            marginBottom: 8,
          }}
        >
          Weekly Summary
        </div>
        <p
          style={{
            fontFamily: 'var(--font-display)',
            fontStyle: 'italic',
            fontSize: 18,
            color: 'var(--text)',
            lineHeight: 1.55,
          }}
        >
          {brief.summary}
        </p>
      </div>

      {/* Action items */}
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
        Your Action Items
      </div>

      <div className="flex flex-col gap-3">
        <AnimatePresence>
          {brief.action_items.map((item, i) => (
            <ActionCard
              key={item.theme_id}
              item={item}
              themeReport={themeReport}
              index={i}
              isFirst={i === 0}
            />
          ))}
        </AnimatePresence>
      </div>
    </section>
  )
}
