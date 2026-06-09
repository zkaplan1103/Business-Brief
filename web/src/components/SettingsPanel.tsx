import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { ScheduleSettings, RunRecord, BusinessMeta } from '../types'

interface Props {
  open: boolean
  onClose: () => void
  schedule: ScheduleSettings
  onSave: (s: ScheduleSettings) => void
  runs: RunRecord[]
  businesses: BusinessMeta[]
  selectedBusiness: string
  onBusinessChange: (id: string) => void
  selectedWeek: string
  onWeekChange: (w: string) => void
  business: BusinessMeta
}

const DAY_LABELS: Record<string, string> = {
  mon: 'Monday', tue: 'Tuesday', wed: 'Wednesday',
  thu: 'Thursday', fri: 'Friday', sat: 'Saturday', sun: 'Sunday',
}

type SaveState = 'idle' | 'saving' | 'saved'

function formatWeek(w: string) {
  const [year, wk] = w.split('-W')
  const jan4 = new Date(parseInt(year), 0, 4)
  const start = new Date(jan4)
  start.setDate(jan4.getDate() - jan4.getDay() + 1 + (parseInt(wk) - 1) * 7)
  const end = new Date(start)
  end.setDate(start.getDate() + 6)
  const fmt = (d: Date) => d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  return `${fmt(start)} – ${fmt(end)}, ${year}`
}

function relativeTime(iso: string) {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
  if (days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days} days ago`
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function nextRun(schedule: ScheduleSettings) {
  if (schedule.cadence === 'off') return 'Off'
  const days = ['sun','mon','tue','wed','thu','fri','sat']
  const idx = days.indexOf(schedule.day_of_week)
  const now = new Date()
  let delta = (idx - now.getDay() + 7) % 7
  if (delta === 0) delta = 7
  const next = new Date(now)
  next.setDate(now.getDate() + delta)
  return next.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' })
}

function duration(a: string, b: string) {
  const s = Math.round((new Date(b).getTime() - new Date(a).getTime()) / 1000)
  return s < 60 ? `${s}s` : `${Math.floor(s/60)}m ${s%60}s`
}

const XIcon = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <line x1="1" y1="1" x2="13" y2="13"/>
    <line x1="13" y1="1" x2="1" y2="13"/>
  </svg>
)

const selectStyle: React.CSSProperties = {
  appearance: 'none', width: '100%',
  background: 'var(--surface-2)', border: '1px solid var(--line-strong)', borderRadius: 8,
  padding: '8px 28px 8px 10px', fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500, color: 'var(--ink)',
  cursor: 'pointer', outline: 'none',
  backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%239CA3AF' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E\")",
  backgroundRepeat: 'no-repeat', backgroundPosition: 'right 8px center',
}

const sectionLabel: React.CSSProperties = {
  fontSize: 10, fontWeight: 700, color: 'var(--ink-faint)',
  letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 14,
}

const fieldLabel: React.CSSProperties = {
  fontSize: 10, fontWeight: 600, color: 'var(--ink-faint)',
  letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 4, display: 'block',
}

export default function SettingsPanel({
  open, onClose, schedule, onSave, runs,
  businesses, selectedBusiness, onBusinessChange,
  selectedWeek, onWeekChange, business,
}: Props) {
  const [settings, setSettings] = useState<ScheduleSettings>(schedule)
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const latest = runs[0]

  useEffect(() => { setSettings(schedule) }, [schedule])

  function handleSave() {
    setSaveState('saving')
    onSave(settings)
    setTimeout(() => { setSaveState('saved'); setTimeout(() => setSaveState('idle'), 1600) }, 350)
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Overlay */}
          <motion.div
            key="overlay"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            style={{ position: 'fixed', inset: 0, zIndex: 200, background: 'rgba(0,0,0,0.25)', backdropFilter: 'blur(2px)' }}
          />

          {/* Panel */}
          <motion.div
            key="panel"
            initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
            transition={{ duration: 0.25, ease: [0.2, 0.8, 0.2, 1] }}
            style={{ position: 'fixed', top: 0, right: 0, bottom: 0, width: 320, background: 'var(--glass-bg)', backdropFilter: 'blur(24px) saturate(1.8)', WebkitBackdropFilter: 'blur(24px) saturate(1.8)', borderLeft: '1px solid var(--glass-border)', boxShadow: '-8px 0 48px rgba(0,0,0,0.18)', zIndex: 201, overflowY: 'auto' }}
          >
            {/* Panel header */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '20px 20px 16px', borderBottom: '1px solid var(--line)' }}>
              <span style={{ fontSize: 17, fontWeight: 700, color: 'var(--ink)' }}>Settings</span>
              <button
                onClick={onClose}
                aria-label="Close settings"
                style={{ width: 32, height: 32, borderRadius: '50%', border: '1px solid var(--line-strong)', background: 'var(--surface-2)', color: 'var(--ink-soft)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0, flexShrink: 0, transition: 'background 0.15s, color 0.15s' }}
                onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface)'; e.currentTarget.style.color = 'var(--ink)' }}
                onMouseLeave={e => { e.currentTarget.style.background = 'var(--surface-2)'; e.currentTarget.style.color = 'var(--ink-soft)' }}
              >
                <XIcon />
              </button>
            </div>

            {/* Business & week */}
            <div style={{ padding: '20px 20px 20px', borderBottom: '1px solid var(--line)', marginBottom: 20 }}>
              <div style={sectionLabel}>Data</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div>
                  <label style={fieldLabel}>Business</label>
                  {businesses.length > 1 ? (
                    <select style={selectStyle} value={selectedBusiness} onChange={e => onBusinessChange(e.target.value)}>
                      {businesses.map(b => <option key={b.business_id} value={b.business_id}>{b.business_name}</option>)}
                    </select>
                  ) : (
                    <div style={{ ...selectStyle, backgroundImage: 'none', paddingRight: 10, cursor: 'default', color: 'var(--ink-soft)' }}>{business.business_name}</div>
                  )}
                </div>
                <div>
                  <label style={fieldLabel}>Week</label>
                  <select style={selectStyle} value={selectedWeek} onChange={e => onWeekChange(e.target.value)}>
                    {business.weeks.map(w => <option key={w} value={w}>{formatWeek(w)}</option>)}
                  </select>
                </div>
              </div>
            </div>

            {/* Schedule section */}
            <div style={{ padding: '0 20px 20px', borderBottom: '1px solid var(--line)', marginBottom: 20 }}>
              <div style={sectionLabel}>Schedule</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>
                <div>
                  <label style={fieldLabel}>Cadence</label>
                  <select style={selectStyle} value={settings.cadence} onChange={e => setSettings(s => ({ ...s, cadence: e.target.value as ScheduleSettings['cadence'] }))}>
                    <option value="weekly">Every week</option>
                    <option value="biweekly">Every 2 weeks</option>
                    <option value="off">Off</option>
                  </select>
                </div>
                {settings.cadence !== 'off' && (
                  <div>
                    <label style={fieldLabel}>Run on</label>
                    <select style={selectStyle} value={settings.day_of_week} onChange={e => setSettings(s => ({ ...s, day_of_week: e.target.value as ScheduleSettings['day_of_week'] }))}>
                      {Object.entries(DAY_LABELS).map(([val, lbl]) => <option key={val} value={val}>{lbl}</option>)}
                    </select>
                  </div>
                )}
              </div>

              {settings.cadence !== 'off' && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 14 }}>
                  {(['draft_only', 'auto_send'] as const).map(mode => {
                    const sel = settings.email_mode === mode
                    return (
                      <label key={mode} style={{ border: `1.5px solid ${sel ? 'var(--brand)' : 'var(--line-strong)'}`, borderRadius: 8, padding: '10px 12px', cursor: 'pointer', background: sel ? 'var(--pos-soft)' : 'var(--surface)', transition: 'all .15s', display: 'block' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 3 }}>
                          <span style={{ width: 13, height: 13, borderRadius: '50%', border: `1.5px solid ${sel ? 'var(--brand)' : 'var(--line-strong)'}`, background: sel ? 'var(--brand)' : 'var(--surface)', flexShrink: 0, position: 'relative', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
                            {sel && <span style={{ width: 5, height: 5, borderRadius: '50%', background: 'white', display: 'block' }} />}
                          </span>
                          <input type="radio" name="email-mode" value={mode} checked={sel} onChange={() => setSettings(s => ({ ...s, email_mode: mode }))} style={{ display: 'none' }} />
                          <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--ink)' }}>{mode === 'draft_only' ? 'Draft only' : 'Auto-send'}</span>
                        </div>
                        <div style={{ fontSize: 10, color: 'var(--ink-faint)', paddingLeft: 20 }}>{mode === 'draft_only' ? 'You review & send' : 'Needs compliance setup'}</div>
                      </label>
                    )
                  })}
                </div>
              )}

              <button
                onClick={handleSave}
                disabled={saveState === 'saving'}
                style={{ display: 'block', width: '100%', background: saveState === 'saved' ? 'var(--pos-soft)' : 'var(--brand)', color: saveState === 'saved' ? 'var(--pos)' : '#fff', border: `1px solid ${saveState === 'saved' ? 'var(--pos)' : 'transparent'}`, borderRadius: 8, padding: 11, fontFamily: 'var(--font-body)', fontSize: 14, fontWeight: 700, cursor: saveState === 'saving' ? 'wait' : 'pointer', transition: 'all .2s', opacity: saveState === 'saving' ? 0.7 : 1 }}
              >
                {saveState === 'saving' ? 'Saving…' : saveState === 'saved' ? '✓ Saved' : 'Save Schedule'}
              </button>
            </div>

            {/* Automation section */}
            <div style={{ padding: '0 20px 24px' }}>
              <div style={sectionLabel}>Automation</div>
              {latest ? (
                <>
                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: latest.status === 'success' ? 'var(--pos-soft)' : latest.status === 'partial' ? 'var(--mix-soft)' : 'var(--neg-soft)', color: latest.status === 'success' ? 'var(--pos)' : latest.status === 'partial' ? 'var(--mix)' : 'var(--neg)', borderRadius: 999, padding: '4px 10px', fontSize: 11, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: 8 }}>
                    <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'currentColor', flexShrink: 0, display: 'inline-block' }} />
                    {latest.status === 'success' ? 'Success' : latest.status === 'partial' ? 'Partial' : 'Failed'}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--ink-faint)', marginBottom: 14 }}>
                    Last run {relativeTime(latest.finished_at)}{schedule.cadence !== 'off' ? ` · Next: ${nextRun(schedule)}` : ''}
                  </div>
                  <div style={{ display: 'flex', gap: 18, paddingTop: 14, borderTop: '1px solid var(--line)' }}>
                    {[{ n: `$${latest.total_cost_usd.toFixed(3)}`, k: 'Cost' }, { n: duration(latest.started_at, latest.finished_at), k: 'Duration' }, { n: `${latest.batches_total - latest.batches_failed}/${latest.batches_total}`, k: 'Batches' }].map(({ n, k }) => (
                      <div key={k}>
                        <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--ink)', lineHeight: 1.1 }}>{n}</div>
                        <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--ink-faint)', letterSpacing: '0.08em', textTransform: 'uppercase', marginTop: 3 }}>{k}</div>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <p style={{ fontSize: 13, color: 'var(--ink-faint)' }}>No runs yet.</p>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
