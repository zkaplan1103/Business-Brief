// Phase 0 shell — renders fixture data confirmation.
// Phase 1 ui-engineer replaces this with the full dashboard.
import './index.css'

function App() {
  return (
    <div style={{ padding: '2rem', fontFamily: 'var(--font-body)', background: 'var(--bg)', minHeight: '100svh' }}>
      <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '2.5rem', color: 'var(--text)', marginBottom: '0.5rem' }}>
        Tideline
      </h1>
      <p style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-body)' }}>
        Phase 0 scaffold — design tokens and fixture types are wired.
        Phase 1 ui-engineer builds the dashboard here.
      </p>
      <div style={{
        marginTop: '1.5rem',
        padding: '1rem',
        background: 'var(--surface)',
        borderRadius: 'var(--radius)',
        boxShadow: 'var(--shadow-card)',
        display: 'inline-block',
      }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', color: 'var(--brand)' }}>
          --brand: #C0694A ✓ &nbsp;
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', color: 'var(--accent-1)' }}>
          --accent-1: #2C5F4A ✓ &nbsp;
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', color: 'var(--accent-2)' }}>
          --accent-2: #E8A23A ✓
        </span>
      </div>
    </div>
  )
}

export default App
