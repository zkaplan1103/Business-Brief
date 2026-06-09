import type { ThemeReport } from '../types'

interface EmptyStateProps {
  themeReport: ThemeReport
}

export default function EmptyState({ themeReport }: EmptyStateProps) {
  return (
    <section
      style={{
        maxWidth: 520,
        margin: '64px auto',
        textAlign: 'center',
        padding: '0 24px',
      }}
      aria-label="Not enough reviews this week"
    >
      <div
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 40,
          color: 'var(--line)',
          lineHeight: 1,
          marginBottom: 24,
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
          color: 'var(--ink)',
          letterSpacing: '-0.02em',
          lineHeight: 1.2,
          marginBottom: 12,
        }}
      >
        A quiet week
      </h2>

      <p
        style={{
          fontFamily: 'var(--font-body)',
          fontSize: 15,
          color: 'var(--ink-soft)',
          lineHeight: 1.7,
          marginBottom: 28,
        }}
      >
        {themeReport.review_count} review{themeReport.review_count !== 1 ? 's' : ''} came in for{' '}
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>{themeReport.week}</span>.
        That's not enough signal to surface a meaningful brief without the risk of reading too much into too little.
      </p>

      <div
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--line)',
          borderRadius: 'var(--radius)',
          padding: '16px 20px',
          textAlign: 'left',
          boxShadow: 'var(--shadow)',
        }}
      >
        <div
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 11,
            fontWeight: 600,
            color: 'var(--ink-soft)',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            marginBottom: 10,
          }}
        >
          What to do
        </div>
        <ul
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 13,
            color: 'var(--ink)',
            lineHeight: 1.75,
            margin: 0,
            paddingLeft: 16,
          }}
        >
          <li>Check back next week — patterns emerge over multiple weeks.</li>
          <li>Enable weekly scheduling so Tideline runs automatically.</li>
          <li>Consider whether your review profile needs attention.</li>
        </ul>
      </div>

      <p
        style={{
          fontFamily: 'var(--font-display)',
          fontStyle: 'italic',
          fontSize: 14,
          color: 'var(--ink-soft)',
          marginTop: 28,
          lineHeight: 1.6,
        }}
      >
        "A quiet week isn't a bad week."
      </p>
    </section>
  )
}
