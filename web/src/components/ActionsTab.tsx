import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { Brief, ThemeReport, ActionItem } from '../types'

interface Props { brief: Brief; themeReport: ThemeReport }

type Filter = 'all' | 'high' | 'medium' | 'low'

const sevConfig = {
  high:   { color: 'var(--neg)', bg: 'var(--neg-soft)', stripe: 'var(--neg)', label: 'High Priority' },
  medium: { color: 'var(--mix)', bg: 'var(--mix-soft)', stripe: 'var(--mix)', label: 'Medium Priority' },
  low:    { color: 'var(--pos)', bg: 'var(--pos-soft)', stripe: 'var(--pos)', label: 'Low Priority' },
} as const

const glass: React.CSSProperties = {
  background: 'var(--glass-bg)',
  backdropFilter: 'blur(16px) saturate(1.6)',
  WebkitBackdropFilter: 'blur(16px) saturate(1.6)',
  border: '1px solid var(--glass-border)',
  boxShadow: 'var(--glass-shadow)',
  borderRadius: 'var(--radius)',
}

function ActionCard({ item, themeReport, index }: { item: ActionItem; themeReport: ThemeReport; index: number }) {
  const [evidenceOpen, setEvidenceOpen] = useState(false)
  const sev = sevConfig[item.severity]
  const theme = themeReport.themes.find(t => t.theme_id === item.theme_id)
  const hasEvidence = !!theme?.sample_quotes.length

  return (
    <motion.article
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: 'easeOut', delay: index * 0.05 }}
      style={{ ...glass, padding: '20px 22px', position: 'relative', overflow: 'hidden', marginBottom: 14 }}
    >
      <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 4, background: sev.stripe }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <span style={{ background: 'var(--surface-2)', border: '1px solid var(--line)', borderRadius: 6, padding: '3px 9px', fontSize: 12, fontWeight: 600, color: 'var(--ink-faint)' }}>#{item.rank}</span>
        <span style={{ borderRadius: 999, padding: '3px 10px', fontSize: 11, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' as const, color: sev.color, background: sev.bg }}>{sev.label}</span>
        {hasEvidence && (
          <button
            onClick={() => setEvidenceOpen(v => !v)}
            style={{ marginLeft: 'auto', background: 'var(--surface)', border: `1px solid ${evidenceOpen ? 'var(--brand)' : 'var(--line-strong)'}`, borderRadius: 999, padding: '5px 13px', fontFamily: 'var(--font-body)', fontSize: 12, fontWeight: 600, color: evidenceOpen ? 'var(--brand)' : 'var(--ink-soft)', cursor: 'pointer', transition: 'all .15s' }}
            aria-expanded={evidenceOpen}
          >
            Evidence {evidenceOpen ? '▴' : '▾'}
          </button>
        )}
      </div>
      <h3 style={{ fontSize: 19, fontWeight: 700, color: 'var(--ink)', lineHeight: 1.3, marginBottom: 7 }}>{item.headline}</h3>
      <p style={{ fontSize: 14, color: 'var(--ink-soft)', lineHeight: 1.6, maxWidth: '64ch', marginBottom: 14 }}>{item.why_it_matters}</p>
      <div style={{ display: 'flex', gap: 10, background: 'var(--surface-2)', borderRadius: 8, padding: '12px 14px', alignItems: 'flex-start' }}>
        <span style={{ fontSize: 10, fontWeight: 800, color: 'var(--brand)', letterSpacing: '0.12em', textTransform: 'uppercase' as const, whiteSpace: 'nowrap' as const, paddingTop: 2 }}>Do this</span>
        <p style={{ fontSize: 13, color: 'var(--ink)', lineHeight: 1.55, margin: 0 }}>{item.recommended_action}</p>
      </div>
      <AnimatePresence>
        {evidenceOpen && hasEvidence && (
          <motion.div key="ev" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.22, ease: 'easeOut' }} style={{ overflow: 'hidden' }}>
            <div style={{ borderTop: '1px dashed var(--line-strong)', paddingTop: 12, marginTop: 14 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--ink-faint)', letterSpacing: '0.12em', textTransform: 'uppercase' as const, marginBottom: 8 }}>
                Sourced from {theme!.review_ids.length} review{theme!.review_ids.length !== 1 ? 's' : ''}
              </div>
              {theme!.sample_quotes.map((q, i) => (
                <div key={i} style={{ fontSize: 13, fontStyle: 'italic', color: 'var(--ink)', padding: '7px 0 7px 14px', borderLeft: '2px solid var(--line-strong)', lineHeight: 1.5, marginBottom: i < theme!.sample_quotes.length - 1 ? 7 : 0 }}>"{q}"</div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  )
}

const filterBtnStyle = (active: boolean, color?: string): React.CSSProperties => ({
  fontFamily: 'var(--font-body)', fontSize: 12, fontWeight: 600,
  borderRadius: 999, padding: '5px 14px', cursor: 'pointer',
  border: `1px solid ${active && color ? color : 'var(--line-strong)'}`,
  background: active && color ? `color-mix(in srgb, ${color} 15%, transparent)` : 'var(--surface)',
  color: active && color ? color : 'var(--ink-soft)',
  transition: 'all 0.15s',
})

function EmailDraft({ brief }: { brief: Brief }) {
  const [open, setOpen] = useState(true)
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    if (!brief.email_draft) return
    await navigator.clipboard.writeText(brief.email_draft)
    setCopied(true)
    setTimeout(() => setCopied(false), 1400)
  }

  return (
    <div style={{ ...glass, overflow: 'hidden', position: 'sticky', top: 92 }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', background: 'transparent', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--ink)' }}>Draft Email</span>
          {!open && brief.email_draft && (
            <span style={{ fontSize: 12, color: 'var(--ink-faint)', fontStyle: 'italic', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const }}>
              {brief.email_draft.split('\n')[0].slice(0, 40)}…
            </span>
          )}
        </div>
        <motion.span animate={{ rotate: open ? 180 : 0 }} transition={{ duration: 0.22 }} style={{ display: 'inline-flex', color: 'var(--ink-faint)', flexShrink: 0 }}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </motion.span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div key="body" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.28, ease: [0.2, 0.8, 0.2, 1] }} style={{ overflow: 'hidden' }}>
            <div style={{ borderTop: '1px solid var(--glass-border)', padding: '16px 20px 20px' }}>
              {brief.email_draft ? (
                <>
                  <pre style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink-soft)', lineHeight: 1.7, whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: '0 0 14px' }}>
                    {brief.email_draft}
                  </pre>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <p style={{ fontSize: 11, color: 'var(--ink-faint)', fontStyle: 'italic' }}>Draft only — review before sending.</p>
                    <button
                      onClick={handleCopy}
                      style={{ background: copied ? 'var(--pos-soft)' : 'var(--surface-2)', border: `1px solid ${copied ? 'var(--pos)' : 'var(--line-strong)'}`, borderRadius: 999, padding: '5px 16px', fontFamily: 'var(--font-body)', fontSize: 12, fontWeight: 600, color: copied ? 'var(--pos)' : 'var(--brand)', cursor: 'pointer', transition: 'all .15s' }}
                    >
                      {copied ? 'Copied ✓' : 'Copy'}
                    </button>
                  </div>
                </>
              ) : (
                <p style={{ fontSize: 13, color: 'var(--ink-faint)' }}>No draft email generated for this week.</p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default function ActionsTab({ brief, themeReport }: Props) {
  const [filter, setFilter] = useState<Filter>('all')
  const items = brief.action_items.filter(item => filter === 'all' || item.severity === filter)

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, ease: 'easeOut' }}>

      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 22, gap: 16 }}>
        <div>
          <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)' }}>Action Items</div>
          <div style={{ fontSize: 13, color: 'var(--ink-soft)', marginTop: 3 }}>{brief.action_items.length} item{brief.action_items.length !== 1 ? 's' : ''} this week · ranked by severity</div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
          <button style={filterBtnStyle(filter === 'all', 'var(--brand)')} onClick={() => setFilter('all')}>All</button>
          <button style={filterBtnStyle(filter === 'high', 'var(--neg)')} onClick={() => setFilter('high')}>High</button>
          <button style={filterBtnStyle(filter === 'medium', 'var(--mix)')} onClick={() => setFilter('medium')}>Medium</button>
          <button style={filterBtnStyle(filter === 'low', 'var(--pos)')} onClick={() => setFilter('low')}>Low</button>
        </div>
      </div>

      {/* Two-column: action list left, email right */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: 20, alignItems: 'start' }}>

        <div>
          <AnimatePresence mode="popLayout">
            {items.map((item, i) => (
              <ActionCard key={item.theme_id} item={item} themeReport={themeReport} index={i} />
            ))}
          </AnimatePresence>
          {items.length === 0 && (
            <div style={{ padding: '32px 24px', ...glass, textAlign: 'center' as const, fontSize: 14, color: 'var(--ink-soft)' }}>
              {filter === 'all' ? 'No action items this week — things look good.' : `No ${filter} priority items this week.`}
            </div>
          )}
        </div>

        <EmailDraft brief={brief} />

      </div>
    </motion.div>
  )
}
