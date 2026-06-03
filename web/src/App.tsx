import { useState, useEffect, useCallback } from 'react'
import './index.css'

import { api } from './api'
import type { Brief, ThemeReport, ScheduleSettings, RunRecord, BusinessMeta } from './types'
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

// When the API returns real data, use it; otherwise fall back to fixtures so
// the UI is always functional (e.g. when running without the API server).
const USE_FIXTURES = false

export default function App() {
  const [businesses, setBusinesses] = useState<BusinessMeta[]>([FIXTURE_BUSINESS])
  const [selectedBusiness, setSelectedBusiness] = useState<string>(FIXTURE_BUSINESS.business_id)
  const [selectedWeek, setSelectedWeek] = useState<string>(FIXTURE_BRIEF.week)

  const [brief, setBrief] = useState<Brief>(FIXTURE_BRIEF)
  const [themeReport, setThemeReport] = useState<ThemeReport>(FIXTURE_THEME_REPORT)
  const [schedule, setSchedule] = useState<ScheduleSettings>(FIXTURE_SCHEDULE)
  const [runs, setRuns] = useState<RunRecord[]>(FIXTURE_RUNS)
  const [loading, setLoading] = useState(false)
  const [apiAvailable, setApiAvailable] = useState(false)

  // Load business list on mount
  useEffect(() => {
    if (USE_FIXTURES) return
    api.businesses()
      .then(biz => {
        if (biz.length > 0) {
          setApiAvailable(true)
          setBusinesses(biz)
          setSelectedBusiness(biz[0].business_id)
          setSelectedWeek(biz[0].weeks[biz[0].weeks.length - 1])
        }
      })
      .catch(() => {
        // API not running — stay on fixtures silently
      })
  }, [])

  // Load brief + schedule + runs when business or week changes
  const loadData = useCallback(async (businessId: string, week: string) => {
    if (!apiAvailable || USE_FIXTURES) return
    setLoading(true)
    try {
      const [briefData, schedData, runsData] = await Promise.all([
        api.brief(businessId, week),
        api.schedule(businessId),
        api.runs(businessId),
      ])
      setBrief(briefData.brief)
      setThemeReport(briefData.themeReport)
      setSchedule(schedData)
      setRuns(runsData)
    } catch {
      // Brief not yet generated for this week — keep current state
    } finally {
      setLoading(false)
    }
  }, [apiAvailable])

  useEffect(() => {
    loadData(selectedBusiness, selectedWeek)
  }, [selectedBusiness, selectedWeek, loadData])

  const handleSaveSchedule = async (settings: ScheduleSettings) => {
    if (!apiAvailable) return
    try {
      const saved = await api.saveSchedule(settings)
      setSchedule(saved)
    } catch {
      // Swallow — SchedulePanel handles its own save-state feedback
    }
  }

  const currentBusiness = businesses.find(b => b.business_id === selectedBusiness)
    ?? FIXTURE_BUSINESS

  return (
    <div style={{ minHeight: '100svh', background: 'var(--bg)' }}>
      <Header
        business={currentBusiness}
        brief={brief}
        themeReport={themeReport}
        selectedWeek={selectedWeek}
        onWeekChange={week => {
          setSelectedWeek(week)
        }}
        businesses={businesses}
        selectedBusiness={selectedBusiness}
        onBusinessChange={biz => {
          setSelectedBusiness(biz)
          const b = businesses.find(x => x.business_id === biz)
          if (b && b.weeks.length > 0) setSelectedWeek(b.weeks[b.weeks.length - 1])
        }}
        loading={loading}
      />

      <main style={{ maxWidth: 1200, margin: '0 auto', padding: '32px 24px 64px' }}>
        {!themeReport.sufficient ? (
          <EmptyState themeReport={themeReport} />
        ) : (
          <>
            <div
              style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr)', gap: 24 }}
              className="main-grid"
            >
              <div>
                <BriefPanel brief={brief} themeReport={themeReport} />
              </div>
              <div className="flex flex-col gap-5">
                <TrendIndicator themeReport={themeReport} brief={brief} />
                <ThemeChart themeReport={themeReport} />
                <SchedulePanel schedule={schedule} onSave={handleSaveSchedule} />
                <RunStatus runs={runs} schedule={schedule} brief={brief} />
              </div>
            </div>

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
