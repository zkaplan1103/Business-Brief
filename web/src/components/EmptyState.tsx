import type { ThemeReport } from '../types'

interface EmptyStateProps {
  themeReport: ThemeReport
}

export default function EmptyState({ themeReport }: EmptyStateProps) {
  return (
    <section
      style={{
        background: 'var(--surface)',
        borderRadius: 'var(--radius)',
        boxShadow: 'var(--shadow-card)',
        padding: '48px 32px',
        textAlign: 'center',
        maxWidth: 560,
        margin: '0 auto',
      }}
      aria-label="Not enough reviews this week"
    >
      {/* Decorative mark */}
      <div
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 48,
          color: 'var(--border)',
          lineHeight: 1,
          marginBottom: 20,
          userSelect: 'none',
        }}
        aria-hidden="true"
      >
        ✦
      </div>

      <h2
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 28,
          fontWeight: 600,
          color: 'var(--text)',
          letterSpacing: '-0.02em',
          lineHeight: 1.2,
          marginBottom: 12,
        }}
      >
        Not enough to call it this week
      </h2>

      <p
        style={{
          fontFamily: 'var(--font-body)',
          fontSize: 15,
          color: 'var(--text-muted)',
          lineHeight: 1.65,
          maxWidth: 400,
          margin: '0 auto 24px',
        }}
      >
        Tideline saw <strong style={{ color: 'var(--text)', fontWeight: 500 }}>{themeReport.review_count} review{themeReport.review_count !== 1 ? 's' : ''}</strong> for <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>{themeReport.week}</span>.
        That's a quiet week — not enough signal to surface a meaningful action brief without the risk of reading too much into too little.
      </p>

      <div
        style={{
          background: 'var(--surface-2)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          padding: '16px 20px',
          textAlign: 'left',
          maxWidth: 380,
          margin: '0 auto',
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
          What to do
        </div>
        <ul
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 13,
            color: 'var(--text)',
            lineHeight: 1.7,
            margin: 0,
            paddingLeft: 18,
          }}
        >
          <li>Check back next week — patterns become clear over multiple weeks.</li>
          <li>Consider enabling weekly scheduling so Tideline runs automatically.</li>
          <li>If reviews aren't coming in, your Yelp profile may need a refresh.</li>
        </ul>
      </div>

      <p
        style={{
          fontFamily: 'var(--font-display)',
          fontStyle: 'italic',
          fontSize: 15,
          color: 'var(--text-muted)',
          marginTop: 24,
          lineHeight: 1.55,
        }}
      >
        "A quiet week isn't a bad week — it's just a quiet one."
      </p>
    </section>
  )
}
