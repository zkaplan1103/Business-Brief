import { useEffect, useState } from 'react'

type Tab = 'overview' | 'charts' | 'actions' | 'cost' | 'eval'

interface HeaderProps {
  loading?: boolean
  activeTab: Tab
  onTabChange: (t: Tab) => void
  onSettingsOpen: () => void
}

function useTheme() {
  const prefersDark = typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches
  const [dark, setDark] = useState(prefersDark)
  useEffect(() => {
    document.documentElement.classList.remove('dark', 'light')
    document.documentElement.classList.add(dark ? 'dark' : 'light')
  }, [dark])
  return { dark, toggle: () => setDark(d => !d) }
}

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'charts',   label: 'Charts' },
  { id: 'actions',  label: 'Actions' },
  { id: 'cost',     label: 'Cost' },
  { id: 'eval',     label: 'Eval' },
]

const GearIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3"/>
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
  </svg>
)

const SunIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="4"/>
    <line x1="12" y1="2" x2="12" y2="4"/><line x1="12" y1="20" x2="12" y2="22"/>
    <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
    <line x1="2" y1="12" x2="4" y2="12"/><line x1="20" y1="12" x2="22" y2="12"/>
    <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
  </svg>
)

const MoonIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
  </svg>
)

const iconBtnStyle: React.CSSProperties = {
  width: 36, height: 36, borderRadius: '50%',
  border: '1px solid var(--glass-border)',
  background: 'var(--glass-bg)',
  backdropFilter: 'blur(12px) saturate(1.4)',
  WebkitBackdropFilter: 'blur(12px) saturate(1.4)',
  boxShadow: 'var(--glass-shadow)',
  color: 'var(--ink-soft)', cursor: 'pointer',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  flexShrink: 0, padding: 0,
  transition: 'background 0.15s, border-color 0.15s, color 0.15s',
}

export default function Header({
  loading, activeTab, onTabChange, onSettingsOpen,
}: HeaderProps) {
  const { dark, toggle } = useTheme()

  return (
    <header style={{ position: 'sticky', top: 0, zIndex: 100 }}>

      {/* Top row: brand | divider | selectors | → icons */}
      <div style={{ background: 'var(--surface)', borderBottom: '1px solid var(--line)', maxWidth: '100%' }}>
      <div style={{ maxWidth: 1180, margin: '0 auto', padding: '0 16px', height: 52, display: 'flex', alignItems: 'center' }}>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, flexShrink: 0 }}>
          <span style={{ fontSize: 19, fontWeight: 700, color: 'var(--brand)', lineHeight: 1, letterSpacing: '-0.01em' }}>BizBrief</span>
          <span style={{ fontSize: 9, fontWeight: 400, color: 'var(--ink-faint)', letterSpacing: '0.14em', textTransform: 'uppercase' as const, lineHeight: 1 }}>Review Brief</span>
        </div>

        {loading && <span style={{ fontSize: 12, color: 'var(--ink-faint)', fontStyle: 'italic', marginLeft: 16 }}>Loading…</span>}

        {/* Spacer pushes icons right */}
        <div style={{ flex: 1 }} />

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <button style={iconBtnStyle} onClick={onSettingsOpen} title="Settings" aria-label="Open settings"
            onMouseEnter={e => { const t = e.currentTarget; t.style.background = 'var(--surface)'; t.style.borderColor = 'var(--brand)'; t.style.color = 'var(--brand)' }}
            onMouseLeave={e => { const t = e.currentTarget; t.style.background = 'var(--glass-bg)'; t.style.borderColor = 'var(--glass-border)'; t.style.color = 'var(--ink-soft)' }}
          ><GearIcon /></button>
          <button style={iconBtnStyle} onClick={toggle} title={dark ? 'Light mode' : 'Dark mode'} aria-label="Toggle dark mode"
            onMouseEnter={e => { const t = e.currentTarget; t.style.background = 'var(--surface)'; t.style.borderColor = 'var(--brand)'; t.style.color = 'var(--brand)' }}
            onMouseLeave={e => { const t = e.currentTarget; t.style.background = 'var(--glass-bg)'; t.style.borderColor = 'var(--glass-border)'; t.style.color = 'var(--ink-soft)' }}
          >{dark ? <SunIcon /> : <MoonIcon />}</button>
        </div>
      </div>
      </div>

      {/* Bottom row: floating tab strip on page background */}
      <nav style={{ maxWidth: 1180, margin: '0 auto', padding: '0 16px', display: 'flex', justifyContent: 'center', alignItems: 'flex-end' }} role="tablist">
        {TABS.map(tab => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            onClick={() => onTabChange(tab.id)}
            style={{
              fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 600,
              color: activeTab === tab.id ? 'var(--brand)' : 'var(--ink-soft)',
              background: 'none', border: 'none',
              borderBottom: `2px solid ${activeTab === tab.id ? 'var(--brand)' : 'transparent'}`,
              padding: '10px 22px 8px',
              cursor: 'pointer', whiteSpace: 'nowrap' as const,
              transition: 'color 0.15s, border-color 0.15s',
            }}
          >
            {tab.label}
          </button>
        ))}
      </nav>

    </header>
  )
}
