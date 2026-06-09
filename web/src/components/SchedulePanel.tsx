import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { ScheduleSettings } from '../types'

interface SchedulePanelProps {
  schedule: ScheduleSettings
  onSave?: (s: ScheduleSettings) => void
}

const DAY_LABELS: Record<string, string> = {
  mon: 'Monday', tue: 'Tuesday', wed: 'Wednesday',
  thu: 'Thursday', fri: 'Friday', sat: 'Saturday', sun: 'Sunday',
}

type SaveState = 'idle' | 'saving' | 'saved'

const miniSelectStyle: React.CSSProperties = {
  width: '100%',
  fontFamily: 'var(--font-body)',
  fontSize: 13,
  fontWeight: 600,
  color: 'var(--ink)',
  background: 'var(--surface)',
  border: '1px solid var(--line-strong)',
  borderRadius: 999,
  padding: '8px 32px 8px 14px',
  cursor: 'pointer',
  appearance: 'none' as const,
  backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%239CA3AF' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E\")",
  backgroundRepeat: 'no-repeat',
  backgroundPosition: 'right 12px center',
  outline: 'none',
}

export default function SchedulePanel({ schedule, onSave }: SchedulePanelProps) {
  const [settings, setSettings] = useState<ScheduleSettings>(schedule)
  const [saveState, setSaveState] = useState<SaveState>('idle')

  function handleSave() {
    setSaveState('saving')
    onSave?.(settings)
    setTimeout(() => {
      setSaveState('saved')
      setTimeout(() => setSaveState('idle'), 1600)
    }, 350)
  }

  const schedMeta = settings.cadence === 'off'
    ? 'Off'
    : `${settings.cadence === 'weekly' ? 'Weekly' : 'Biweekly'} · ${settings.email_mode === 'draft_only' ? 'draft only' : 'auto-send'}`

  return (
    <section
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--line)',
        borderRadius: 'var(--radius)',
        boxShadow: 'var(--shadow)',
      }}
      aria-label="Schedule settings"
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          padding: '18px 20px 0',
        }}
      >
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 17, fontWeight: 600 }}>
          Schedule
        </h2>
        <span style={{ fontSize: 11, color: 'var(--ink-faint)', fontStyle: 'italic' }}>
          {schedMeta}
        </span>
      </div>

      <div style={{ padding: '16px 20px 20px' }}>
        {/* Cadence + Day row */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
          <div>
            <label
              htmlFor="cadence-select"
              style={{
                display: 'block',
                fontSize: 10,
                letterSpacing: '.14em',
                textTransform: 'uppercase' as const,
                color: 'var(--ink-faint)',
                marginBottom: 6,
              }}
            >
              Cadence
            </label>
            <select
              id="cadence-select"
              value={settings.cadence}
              onChange={e => setSettings(s => ({ ...s, cadence: e.target.value as ScheduleSettings['cadence'] }))}
              style={miniSelectStyle}
            >
              <option value="weekly">Every week</option>
              <option value="biweekly">Every 2 weeks</option>
              <option value="off">Off</option>
            </select>
          </div>

          {settings.cadence !== 'off' && (
            <div>
              <label
                htmlFor="day-select"
                style={{
                  display: 'block',
                  fontSize: 10,
                  letterSpacing: '.14em',
                  textTransform: 'uppercase' as const,
                  color: 'var(--ink-faint)',
                  marginBottom: 6,
                }}
              >
                Run on
              </label>
              <select
                id="day-select"
                value={settings.day_of_week}
                onChange={e => setSettings(s => ({ ...s, day_of_week: e.target.value as ScheduleSettings['day_of_week'] }))}
                style={miniSelectStyle}
              >
                {Object.entries(DAY_LABELS).map(([val, label]) => (
                  <option key={val} value={val}>{label}</option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Email mode radios */}
        {settings.cadence !== 'off' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
            {(['draft_only', 'auto_send'] as const).map(mode => {
              const sel = settings.email_mode === mode
              return (
                <label
                  key={mode}
                  style={{
                    border: `1px solid ${sel ? 'var(--pos)' : 'var(--line-strong)'}`,
                    borderRadius: 10,
                    padding: '11px 12px',
                    cursor: 'pointer',
                    background: sel ? 'var(--pos-soft)' : 'var(--surface)',
                    transition: 'all .15s',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 13, fontWeight: 700 }}>
                    {/* Custom radio dot */}
                    <span
                      style={{
                        width: 14, height: 14,
                        borderRadius: '50%',
                        border: `2px solid ${sel ? 'var(--pos)' : 'var(--line-strong)'}`,
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0,
                        position: 'relative' as const,
                      }}
                    >
                      {sel && (
                        <span
                          style={{
                            position: 'absolute' as const,
                            inset: 2,
                            borderRadius: '50%',
                            background: 'var(--pos)',
                          }}
                        />
                      )}
                    </span>
                    <input
                      type="radio"
                      name="email-mode"
                      value={mode}
                      checked={sel}
                      onChange={() => setSettings(s => ({ ...s, email_mode: mode }))}
                      style={{ display: 'none' }}
                    />
                    {mode === 'draft_only' ? 'Draft only' : 'Auto-send'}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--ink-faint)', marginTop: 3, marginLeft: 21 }}>
                    {mode === 'draft_only' ? 'You review & send' : 'Needs compliance setup'}
                  </div>
                </label>
              )
            })}
          </div>
        )}

        {/* Save button */}
        <button
          onClick={handleSave}
          disabled={saveState === 'saving'}
          style={{
            width: '100%',
            fontFamily: 'var(--font-body)',
            fontSize: 14,
            fontWeight: 700,
            color: saveState === 'saved' ? 'var(--pos)' : '#fff',
            background: saveState === 'saved' ? 'var(--pos-soft)' : 'var(--cta)',
            border: `1px solid ${saveState === 'saved' ? 'var(--pos)' : 'transparent'}`,
            borderRadius: 10,
            padding: '12px',
            cursor: saveState === 'saving' ? 'wait' : 'pointer',
            transition: 'all .2s ease',
            opacity: saveState === 'saving' ? 0.7 : 1,
          }}
        >
          <AnimatePresence mode="wait">
            {saveState === 'saving' && (
              <motion.span key="saving" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }}>
                Saving…
              </motion.span>
            )}
            {saveState === 'saved' && (
              <motion.span key="saved" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
                ✓ Saved
              </motion.span>
            )}
            {saveState === 'idle' && (
              <motion.span key="save" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }}>
                Save schedule
              </motion.span>
            )}
          </AnimatePresence>
        </button>
      </div>
    </section>
  )
}
