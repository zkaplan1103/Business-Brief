import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { ScheduleSettings } from '../types'

interface SchedulePanelProps {
  schedule: ScheduleSettings
  onSave?: (s: ScheduleSettings) => void
}

const DAY_LABELS: Record<string, string> = {
  mon: 'Monday',
  tue: 'Tuesday',
  wed: 'Wednesday',
  thu: 'Thursday',
  fri: 'Friday',
  sat: 'Saturday',
  sun: 'Sunday',
}

const CADENCE_LABELS: Record<string, string> = {
  weekly: 'Every week',
  biweekly: 'Every two weeks',
  off: 'Off',
}

type SaveState = 'idle' | 'saving' | 'saved'

export default function SchedulePanel({ schedule, onSave }: SchedulePanelProps) {
  const [settings, setSettings] = useState<ScheduleSettings>(schedule)
  const [saveState, setSaveState] = useState<SaveState>('idle')

  function handleSave() {
    setSaveState('saving')
    onSave?.(settings)
    setTimeout(() => {
      setSaveState('saved')
      setTimeout(() => setSaveState('idle'), 1800)
    }, 400)
  }

  const selectStyle = {
    fontFamily: 'var(--font-body)',
    fontSize: 14,
    color: 'var(--text)',
    background: 'var(--surface-2)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius)',
    padding: '8px 12px',
    width: '100%',
    outline: 'none',
    cursor: 'pointer',
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
      aria-label="Schedule settings"
    >
      <div
        style={{
          fontFamily: 'var(--font-body)',
          fontSize: 11,
          fontWeight: 600,
          color: 'var(--text-muted)',
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          marginBottom: 4,
        }}
      >
        Automation Schedule
      </div>
      <h2
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 18,
          fontWeight: 600,
          color: 'var(--text)',
          marginBottom: 20,
        }}
      >
        Brief delivery settings
      </h2>

      <div className="flex flex-col gap-4">
        {/* Cadence */}
        <div>
          <label
            htmlFor="cadence-select"
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 12,
              fontWeight: 600,
              color: 'var(--text-muted)',
              letterSpacing: '0.04em',
              textTransform: 'uppercase',
              display: 'block',
              marginBottom: 6,
            }}
          >
            Cadence
          </label>
          <select
            id="cadence-select"
            value={settings.cadence}
            onChange={e => setSettings(s => ({ ...s, cadence: e.target.value as ScheduleSettings['cadence'] }))}
            style={selectStyle}
            onFocus={e => { e.currentTarget.style.boxShadow = '0 0 0 3px var(--focus-ring)' }}
            onBlur={e => { e.currentTarget.style.boxShadow = 'none' }}
          >
            <option value="weekly">Every week</option>
            <option value="biweekly">Every two weeks</option>
            <option value="off">Off</option>
          </select>
        </div>

        {/* Day of week */}
        {settings.cadence !== 'off' && (
          <div>
            <label
              htmlFor="day-select"
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 12,
                fontWeight: 600,
                color: 'var(--text-muted)',
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
                display: 'block',
                marginBottom: 6,
              }}
            >
              Run on
            </label>
            <select
              id="day-select"
              value={settings.day_of_week}
              onChange={e => setSettings(s => ({ ...s, day_of_week: e.target.value as ScheduleSettings['day_of_week'] }))}
              style={selectStyle}
              onFocus={e => { e.currentTarget.style.boxShadow = '0 0 0 3px var(--focus-ring)' }}
              onBlur={e => { e.currentTarget.style.boxShadow = 'none' }}
            >
              {Object.entries(DAY_LABELS).map(([val, label]) => (
                <option key={val} value={val}>{label}</option>
              ))}
            </select>
          </div>
        )}

        {/* Email mode */}
        <div>
          <div
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 12,
              fontWeight: 600,
              color: 'var(--text-muted)',
              letterSpacing: '0.04em',
              textTransform: 'uppercase',
              marginBottom: 8,
            }}
          >
            Email mode
          </div>
          <div className="flex flex-col gap-2">
            {(['draft_only', 'auto_send'] as const).map(mode => (
              <label
                key={mode}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 10,
                  cursor: 'pointer',
                  padding: '10px 12px',
                  background: settings.email_mode === mode ? 'color-mix(in srgb, var(--accent-1) 10%, var(--surface))' : 'var(--surface-2)',
                  border: `1px solid ${settings.email_mode === mode ? 'var(--accent-1)' : 'var(--border)'}`,
                  borderRadius: 'var(--radius)',
                  transition: 'all 0.15s ease',
                }}
              >
                <input
                  type="radio"
                  name="email-mode"
                  value={mode}
                  checked={settings.email_mode === mode}
                  onChange={() => setSettings(s => ({ ...s, email_mode: mode }))}
                  style={{ marginTop: 2, accentColor: 'var(--accent-1)', flexShrink: 0 }}
                />
                <div>
                  <div
                    style={{
                      fontFamily: 'var(--font-body)',
                      fontSize: 14,
                      fontWeight: 500,
                      color: 'var(--text)',
                    }}
                  >
                    {mode === 'draft_only' ? 'Draft only' : 'Auto-send'}
                  </div>
                  <div
                    style={{
                      fontFamily: 'var(--font-body)',
                      fontSize: 12,
                      color: 'var(--text-muted)',
                      lineHeight: 1.4,
                    }}
                  >
                    {mode === 'draft_only'
                      ? 'Generate a draft — you review and send.'
                      : 'Send automatically. Requires CAN-SPAM / GDPR compliance setup.'}
                  </div>
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Preview */}
        {settings.cadence !== 'off' && (
          <div
            style={{
              background: 'var(--surface-2)',
              borderRadius: 'var(--radius)',
              border: '1px solid var(--border)',
              padding: '10px 14px',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 12,
                color: 'var(--text-muted)',
              }}
            >
              Brief runs {CADENCE_LABELS[settings.cadence].toLowerCase()} on {DAY_LABELS[settings.day_of_week]}s,
              email as {settings.email_mode === 'draft_only' ? 'draft' : 'auto-send'}.
            </span>
          </div>
        )}

        {/* Save button */}
        <button
          onClick={handleSave}
          disabled={saveState === 'saving'}
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 14,
            fontWeight: 600,
            color: saveState === 'saved' ? 'var(--accent-1)' : '#fff',
            background: saveState === 'saved' ? 'color-mix(in srgb, var(--accent-1) 10%, var(--surface))' : 'var(--brand)',
            border: `1px solid ${saveState === 'saved' ? 'var(--accent-1)' : 'transparent'}`,
            borderRadius: 'var(--radius)',
            padding: '10px 20px',
            cursor: saveState === 'saving' ? 'wait' : 'pointer',
            transition: 'all 0.2s ease',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            width: '100%',
            opacity: saveState === 'saving' ? 0.7 : 1,
          }}
          aria-label="Save schedule settings"
        >
          <AnimatePresence mode="wait">
            {saveState === 'saving' && (
              <motion.span
                key="saving"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
              >
                Saving…
              </motion.span>
            )}
            {saveState === 'saved' && (
              <motion.span
                key="saved"
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                transition={{ duration: 0.15 }}
                style={{ display: 'flex', alignItems: 'center', gap: 6 }}
              >
                <span>✓</span> Saved
              </motion.span>
            )}
            {saveState === 'idle' && (
              <motion.span
                key="save"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
              >
                Save schedule
              </motion.span>
            )}
          </AnimatePresence>
        </button>
      </div>
    </article>
  )
}
