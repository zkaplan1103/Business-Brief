import { useState, useEffect, useCallback } from 'react'
import './index.css'

import { api } from './api'
import type { Brief, ThemeReport, ScheduleSettings, RunRecord, BusinessMeta } from './types'
import { FIXTURE_BRIEF, FIXTURE_THEME_REPORT, FIXTURE_SCHEDULE, FIXTURE_RUNS, FIXTURE_BUSINESS } from './fixtures'

import Header from './components/Header'
import OverviewTab from './components/OverviewTab'
import ChartsTab from './components/ChartsTab'
import ActionsTab from './components/ActionsTab'
import CostTab from './components/CostTab'
import EvalTab from './components/EvalTab'
import SettingsPanel from './components/SettingsPanel'
import EmptyState from './components/EmptyState'

type Tab = 'overview' | 'charts' | 'actions' | 'cost' | 'eval'

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
  const [activeTab, setActiveTab] = useState<Tab>('overview')
  const [settingsOpen, setSettingsOpen] = useState(false)

  useEffect(() => {
    if (USE_FIXTURES) return
    api.businesses().then(biz => {
      if (biz.length > 0) {
        setApiAvailable(true)
        setBusinesses(biz)
        setSelectedBusiness(biz[0].business_id)
        setSelectedWeek(biz[0].weeks[biz[0].weeks.length - 1])
      }
    }).catch(() => {})
  }, [])

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
    } catch { /* keep current state */ } finally { setLoading(false) }
  }, [apiAvailable])

  useEffect(() => { loadData(selectedBusiness, selectedWeek) }, [selectedBusiness, selectedWeek, loadData])

  const handleSaveSchedule = async (settings: ScheduleSettings) => {
    if (!apiAvailable) return
    try { const saved = await api.saveSchedule(settings); setSchedule(saved) } catch {}
  }

  const currentBusiness = businesses.find(b => b.business_id === selectedBusiness) ?? FIXTURE_BUSINESS

  return (
    <div style={{ minHeight: '100svh', background: 'var(--bg)' }}>
      <Header
        loading={loading}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onSettingsOpen={() => setSettingsOpen(true)}
      />

      <main style={{ maxWidth: 1180, margin: '0 auto', padding: '28px 16px 64px' }}>
        {activeTab === 'cost' ? (
          <CostTab />
        ) : activeTab === 'eval' ? (
          <EvalTab />
        ) : !themeReport.sufficient ? (
          <EmptyState themeReport={themeReport} />
        ) : (
          <>
            {activeTab === 'overview' && <OverviewTab brief={brief} themeReport={themeReport} onTabChange={setActiveTab} />}
            {activeTab === 'charts'   && <ChartsTab themeReport={themeReport} />}
            {activeTab === 'actions'  && <ActionsTab brief={brief} themeReport={themeReport} />}
          </>
        )}
      </main>

      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        schedule={schedule}
        onSave={handleSaveSchedule}
        runs={runs}
        businesses={businesses}
        selectedBusiness={selectedBusiness}
        onBusinessChange={biz => {
          setSelectedBusiness(biz)
          const b = businesses.find(x => x.business_id === biz)
          if (b?.weeks.length) setSelectedWeek(b.weeks[b.weeks.length - 1])
        }}
        selectedWeek={selectedWeek}
        onWeekChange={week => setSelectedWeek(week)}
        business={currentBusiness}
      />
    </div>
  )
}
