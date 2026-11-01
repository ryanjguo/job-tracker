import { useCallback, useEffect, useState } from 'react'
import { api, errorMessage, type Application, type Meta, type Stats, type Status } from './api'
import { Board } from './components/Board'
import { Header } from './components/Header'
import { StatsStrip } from './components/StatsStrip'
import { TableView } from './components/TableView'
import './App.css'

type View = 'board' | 'table'
type Notice = { kind: 'ok' | 'error'; text: string } | null

function App() {
  const [apps, setApps] = useState<Application[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [meta, setMeta] = useState<Meta | null>(null)
  const [view, setView] = useState<View>('board')
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [notice, setNotice] = useState<Notice>(null)

  const load = useCallback(
    () =>
      Promise.all([api.applications(), api.stats(), api.meta()]).then(
        ([a, s, m]) => {
          setApps(a)
          setStats(s)
          setMeta(m)
        },
        (e) => setNotice({ kind: 'error', text: errorMessage(e) }),
      ),
    [],
  )

  useEffect(() => {
    load().finally(() => setLoading(false))
  }, [load])


  const changeStatus = async (id: number, status: Status) => {
    const before = apps
    // optimistic: move the card right away, roll back if the API says no
    setApps((cur) => cur.map((a) => (a.id === id ? { ...a, status, possibly_ghosted: false } : a)))
    try {
      const updated = await api.updateApplication(id, { status })
      setApps((cur) => cur.map((a) => (a.id === id ? updated : a)))
      setStats(await api.stats())
    } catch (e) {
      setApps(before)
      setNotice({ kind: 'error', text: `Couldn't change status: ${errorMessage(e)}` })
    }
  }

  const syncNow = async () => {
    setSyncing(true)
    setNotice(null)
    try {
      const s = await api.sync()
      const parts = [`${s.created} new`, `${s.duplicates} duplicates`, `${s.review} to review`, `${s.ignored} skipped`]
      const errors = s.errors.length ? ` · ${s.errors.length} errors` : ''
      setNotice({ kind: 'ok', text: `Scanned ${s.scanned} emails since ${s.since}: ${parts.join(', ')}${errors}.` })
      await load()
    } catch (e) {
      setNotice({ kind: 'error', text: `Sync failed: ${errorMessage(e)}` })
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="page">
      <Header meta={meta} syncing={syncing} onSync={syncNow} />

      {notice && (
        <div className={`notice notice--${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'}>
          <span>{notice.text}</span>
          <button type="button" className="link-button" onClick={() => setNotice(null)} aria-label="Dismiss">
            ×
          </button>
        </div>
      )}

      <StatsStrip stats={stats} />

      <nav className="tabs" aria-label="Views">
        <button type="button" className={view === 'board' ? 'tab tab--active' : 'tab'} onClick={() => setView('board')}>
          Board
        </button>
        <button type="button" className={view === 'table' ? 'tab tab--active' : 'tab'} onClick={() => setView('table')}>
          Table
        </button>
      </nav>

      <main>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : view === 'board' ? (
          <Board apps={apps} onStatus={changeStatus} />
        ) : (
          <TableView apps={apps} onStatus={changeStatus} />
        )}
      </main>
    </div>
  )
}

export default App
