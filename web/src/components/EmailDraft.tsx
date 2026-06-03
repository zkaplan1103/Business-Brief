import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { Brief } from '../types'

interface EmailDraftProps {
  brief: Brief
}

export default function EmailDraft({ brief }: EmailDraftProps) {
  const [copied, setCopied] = useState(false)

  if (!brief.email_draft) return null

  async function handleCopy() {
    await navigator.clipboard.writeText(brief.email_draft!)
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  return (
    <article
      style={{
        background: 'var(--surface)',
        borderRadius: 'var(--radius)',
        boxShadow: 'var(--shadow-raised)',
        padding: '20px 24px',
        border: '1px solid var(--border)',
      }}
    >
      <div className="flex items-center justify-between gap-4 mb-4 flex-wrap">
        <div>
          <div
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 11,
              fontWeight: 600,
              color: 'var(--text-muted)',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              marginBottom: 2,
            }}
          >
            Draft Email
          </div>
          <h2
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 18,
              fontWeight: 600,
              color: 'var(--text)',
            }}
          >
            Ready to send — review then copy
          </h2>
        </div>

        <button
          onClick={handleCopy}
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 13,
            fontWeight: 600,
            color: copied ? 'var(--accent-1)' : 'var(--brand)',
            background: copied ? 'color-mix(in srgb, var(--accent-1) 10%, var(--surface))' : 'var(--surface-2)',
            border: `1px solid ${copied ? 'var(--accent-1)' : 'var(--border)'}`,
            borderRadius: 'var(--radius)',
            padding: '8px 16px',
            cursor: 'pointer',
            transition: 'all 0.2s ease',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            minWidth: 100,
            justifyContent: 'center',
          }}
          aria-label="Copy email draft to clipboard"
        >
          <AnimatePresence mode="wait">
            {copied ? (
              <motion.span
                key="copied"
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                transition={{ duration: 0.15 }}
                style={{ display: 'flex', alignItems: 'center', gap: 6 }}
              >
                <span style={{ fontSize: 16 }}>✓</span> Copied
              </motion.span>
            ) : (
              <motion.span
                key="copy"
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                transition={{ duration: 0.15 }}
              >
                Copy
              </motion.span>
            )}
          </AnimatePresence>
        </button>
      </div>

      <div
        style={{
          background: 'var(--surface-2)',
          borderRadius: 'var(--radius)',
          border: '1px solid var(--border)',
          padding: '16px 20px',
        }}
      >
        <pre
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 13,
            color: 'var(--text)',
            lineHeight: 1.7,
            margin: 0,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {brief.email_draft}
        </pre>
      </div>

      <p
        style={{
          fontFamily: 'var(--font-body)',
          fontSize: 12,
          color: 'var(--text-muted)',
          marginTop: 10,
          lineHeight: 1.55,
        }}
      >
        Draft only — a human sends this. Review before sharing.
      </p>
    </article>
  )
}
