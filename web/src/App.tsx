import { useState, useEffect } from 'react'
import './index.css'

import { api, DEMO } from './api'
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
import DemoBanner from './components/DemoBanner'

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

  // Loading is derived (selection differs from what was last loaded) rather
  // than set synchronously inside the effect.
  const selectionKey = `${selectedBusiness}/${selectedWeek}`
  const [loadedKey, setLoadedKey] = useState(selectionKey)
  const loading = apiAvailable && !USE_FIXTURES && loadedKey !== selectionKey

  useEffect(() => {
    if (!apiAvailable || USE_FIXTURES) return
    Promise.all([
      api.brief(selectedBusiness, selectedWeek),
      api.schedule(selectedBusiness),
      api.runs(selectedBusiness),
    ]).then(([briefData, schedData, runsData]) => {
      setBrief(briefData.brief)
      setThemeReport(briefData.themeReport)
      setSchedule(schedData)
      setRuns(runsData)
    }).catch(() => { /* keep current state */ })
      .finally(() => setLoadedKey(`${selectedBusiness}/${selectedWeek}`))
  }, [apiAvailable, selectedBusiness, selectedWeek])

  const handleSaveSchedule = async (settings: ScheduleSettings) => {
    if (!apiAvailable) return
    try { const saved = await api.saveSchedule(settings); setSchedule(saved) } catch { /* keep current state */ }
  }

  const currentBusiness = businesses.find(b => b.business_id === selectedBusiness) ?? FIXTURE_BUSINESS

  const changeBusiness = (biz: string) => {
    setSelectedBusiness(biz)
    const b = businesses.find(x => x.business_id === biz)
    if (b?.weeks.length) setSelectedWeek(b.weeks[b.weeks.length - 1])
  }

  return (
    <div style={{ minHeight: '100svh', background: 'var(--bg)' }}>
      <Header
        loading={loading}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onSettingsOpen={DEMO ? undefined : () => setSettingsOpen(true)}
      />

      {DEMO && (
        <DemoBanner
          businesses={businesses}
          selectedBusiness={selectedBusiness}
          onBusinessChange={changeBusiness}
          weeks={currentBusiness.weeks}
          selectedWeek={selectedWeek}
          onWeekChange={setSelectedWeek}
        />
      )}

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

      {!DEMO && <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        schedule={schedule}
        onSave={handleSaveSchedule}
        runs={runs}
        businesses={businesses}
        selectedBusiness={selectedBusiness}
        onBusinessChange={changeBusiness}
        selectedWeek={selectedWeek}
        onWeekChange={week => setSelectedWeek(week)}
        business={currentBusiness}
      />}
    </div>
  )
}
