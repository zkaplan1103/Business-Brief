import { useState } from 'react'
import './index.css'

import {
  FIXTURE_BRIEF,
  FIXTURE_THEME_REPORT,
  FIXTURE_SCHEDULE,
  FIXTURE_RUNS,
  FIXTURE_BUSINESS,
} from './fixtures'

import Header from './components/Header'
import BriefPanel from './components/BriefPanel'
import ThemeChart from './components/ThemeChart'
import TrendIndicator from './components/TrendIndicator'
import EmailDraft from './components/EmailDraft'
import SchedulePanel from './components/SchedulePanel'
import RunStatus from './components/RunStatus'
import EmptyState from './components/EmptyState'

export default function App() {
  const [selectedWeek, setSelectedWeek] = useState(FIXTURE_BRIEF.week)

  // Phase 2: swap these for API calls keyed on selectedWeek
  const brief = FIXTURE_BRIEF
  const themeReport = FIXTURE_THEME_REPORT

  return (
    <div
      style={{
        minHeight: '100svh',
        background: 'var(--bg)',
      }}
    >
      <Header
        business={FIXTURE_BUSINESS}
        brief={brief}
        themeReport={themeReport}
        selectedWeek={selectedWeek}
        onWeekChange={setSelectedWeek}
      />

      <main
        style={{
          maxWidth: 1200,
          margin: '0 auto',
          padding: '32px 24px 64px',
        }}
      >
        {!themeReport.sufficient ? (
          <EmptyState themeReport={themeReport} />
        ) : (
          <>
            {/* Two-column layout: brief left ~60%, right panel ~40% */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(0,1fr)',
                gap: 24,
              }}
              className="main-grid"
            >
              {/* Left: Brief */}
              <div>
                <BriefPanel brief={brief} themeReport={themeReport} />
              </div>

              {/* Right: chart + trend + schedule + run status */}
              <div className="flex flex-col gap-5">
                <TrendIndicator themeReport={themeReport} brief={brief} />
                <ThemeChart themeReport={themeReport} />
                <SchedulePanel schedule={FIXTURE_SCHEDULE} />
                <RunStatus runs={FIXTURE_RUNS} schedule={FIXTURE_SCHEDULE} brief={brief} />
              </div>
            </div>

            {/* Email draft — below the fold */}
            {brief.email_draft && (
              <div style={{ marginTop: 32 }}>
                <EmailDraft brief={brief} />
              </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}
