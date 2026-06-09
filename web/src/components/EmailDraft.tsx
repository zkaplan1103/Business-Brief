import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { Brief } from '../types'

interface EmailDraftProps {
  brief: Brief
}

export default function EmailDraft({ brief }: EmailDraftProps) {
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  if (!brief.email_draft) return null

  async function handleCopy(e: React.MouseEvent) {
    e.stopPropagation()
    await navigator.clipboard.writeText(brief.email_draft!)
    setCopied(true)
    setTimeout(() => setCopied(false), 1400)
  }

  return (
    <section
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--line)',
        borderRadius: 'var(--radius)',
        boxShadow: 'var(--shadow)',
        overflow: 'hidden',
      }}
      aria-label="Draft email"
    >
      {/* Header — click to toggle */}
      <div
        onClick={() => setOpen(v => !v)}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '16px 20px',
          cursor: 'pointer',
          userSelect: 'none',
        }}
      >
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 17, fontWeight: 600 }}>
          Draft email
        </h2>
        <button
          onClick={handleCopy}
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 12,
            fontWeight: 600,
            color: copied ? 'var(--pos)' : 'var(--brand)',
            background: 'var(--surface)',
            border: `1px solid ${copied ? 'var(--pos)' : 'var(--line-strong)'}`,
            borderRadius: 999,
            padding: '6px 14px',
            cursor: 'pointer',
            transition: 'all .15s',
          }}
        >
          {copied ? 'Copied ✓' : 'Copy'}
        </button>
      </div>

      {/* Collapsible body */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="body"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
            style={{ overflow: 'hidden' }}
          >
            <div
              style={{
                padding: '0 20px 20px',
                borderTop: '1px solid var(--line)',
              }}
            >
              <pre
                style={{
                  fontFamily: 'var(--font-body)',
                  fontSize: 13,
                  color: 'var(--ink-soft)',
                  lineHeight: 1.6,
                  margin: '14px 0 0',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {brief.email_draft}
              </pre>
              <p
                style={{
                  fontSize: 11,
                  color: 'var(--ink-faint)',
                  fontStyle: 'italic',
                  marginTop: 14,
                }}
              >
                Draft only — review before sending.
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}
