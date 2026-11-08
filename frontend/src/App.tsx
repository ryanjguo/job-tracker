import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, errorMessage, type Application, type ApplicationInput, type Meta, type Stats, type Status } from './api'
import { ApplicationModal } from './components/ApplicationModal'
import { Board } from './components/Board'
import { FilterBar } from './components/FilterBar'
import { Header } from './components/Header'
import { ReviewQueue } from './components/ReviewQueue'
import { StatsStrip } from './components/StatsStrip'
import { TableView } from './components/TableView'
import { applyFilters, isFiltering, NO_FILTERS, termsOf, type Filters } from './filters'
import './App.css'

type View = 'board' | 'table' | 'review'
type Notice = { kind: 'ok' | 'error'; text: string } | null

function App() {
  const [apps, setApps] = useState<Application[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [meta, setMeta] = useState<Meta | null>(null)
  const [view, setView] = useState<View>('board')
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [notice, setNotice] = useState<Notice>(null)
  // null = closed, 'new' = add form, otherwise the application being edited
  const [editing, setEditing] = useState<Application | 'new' | null>(null)
  const [syncCount, setSyncCount] = useState(0) // remounts the review list after a sync
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const shown = useMemo(() => applyFilters(apps, filters), [apps, filters])
  const terms = useMemo(() => termsOf(apps), [apps])

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

  // Pick up background syncs (SYNC_EVERY_MINUTES): check /api/meta once a minute and reload
  // everything when a sync has finished since we last looked.
  const lastSync = useRef<string | null | undefined>(undefined)
  useEffect(() => {
    if (meta) lastSync.current = meta.last_sync_at
  }, [meta])
  useEffect(() => {
    const timer = setInterval(async () => {
      if (document.hidden) return
      try {
        const m = await api.meta()
        if (lastSync.current !== undefined && m.last_sync_at !== lastSync.current) {
          await load()
          setSyncCount((n) => n + 1)
        } else {
          setMeta(m)
        }
      } catch {
        // backend restarting etc.: try again next minute
      }
    }, 60_000)
    return () => clearInterval(timer)
  }, [load])

  const showError = useCallback((text: string) => setNotice({ kind: 'error', text }), [])

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
      setSyncCount((n) => n + 1)
      await load()
    } catch (e) {
      setNotice({ kind: 'error', text: `Sync failed: ${errorMessage(e)}` })
    } finally {
      setSyncing(false)
    }
  }

  const save = async (input: ApplicationInput) => {
    if (editing === 'new') {
      const created = await api.createApplication(input)
      setNotice({ kind: 'ok', text: `Added ${created.company}.` })
    } else if (editing) {
      await api.updateApplication(editing.id, input)
    }
    setEditing(null)
    await load()
  }

  const remove = async () => {
    if (!editing || editing === 'new') return
    await api.deleteApplication(editing.id)
    setNotice({ kind: 'ok', text: `Deleted ${editing.company}.` })
    setEditing(null)
    await load()
  }

  const reviewCount = meta?.review_count ?? 0

  return (
    <div className="page">
      <Header meta={meta} syncing={syncing} onSync={syncNow}>
        <button type="button" className="primary" onClick={() => setEditing('new')}>
          + Add
        </button>
      </Header>

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
        <button type="button" className={view === 'review' ? 'tab tab--active' : 'tab'} onClick={() => setView('review')}>
          Review{' '}
          <span className={reviewCount ? 'count count--alert' : 'count'} aria-label={`${reviewCount} to review`}>
            {reviewCount}
          </span>
        </button>
      </nav>

      {view !== 'review' && !loading && apps.length > 0 && (
        <FilterBar filters={filters} onChange={setFilters} terms={terms} shown={shown.length} total={apps.length} />
      )}

      <main>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : view === 'board' ? (
          <Board apps={shown} onStatus={changeStatus} onOpen={setEditing} />
        ) : view === 'table' ? (
          <TableView apps={shown} filtered={isFiltering(filters)} onStatus={changeStatus} onOpen={setEditing} />
        ) : (
          <ReviewQueue key={syncCount} onChanged={load} onError={showError} />
        )}
      </main>

      {editing && (
        <ApplicationModal
          key={editing === 'new' ? 'new' : editing.id}
          app={editing === 'new' ? null : editing}
          onSave={save}
          onDelete={editing === 'new' ? undefined : remove}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}

export default App
