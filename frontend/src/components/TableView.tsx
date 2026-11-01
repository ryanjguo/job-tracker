import { useMemo, useState } from 'react'
import { STATUSES, STATUS_LABEL, followUpDue, type Application, type Status } from '../api'
import { formatDate, todayISO } from '../format'

type SortKey = 'company' | 'role' | 'location' | 'term' | 'status' | 'applied_date' | 'follow_up_date' | 'ats'

const COLUMNS: [SortKey, string][] = [
  ['company', 'Company'],
  ['role', 'Role'],
  ['location', 'Location'],
  ['term', 'Term'],
  ['status', 'Status'],
  ['applied_date', 'Applied'],
  ['follow_up_date', 'Follow up'],
  ['ats', 'Source'],
]

interface Props {
  apps: Application[]
  onStatus: (id: number, status: Status) => void
  onOpen?: (app: Application) => void
}

export function TableView({ apps, onStatus, onOpen }: Props) {
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'applied_date', dir: -1 })

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    const filtered = q
      ? apps.filter((a) => [a.company, a.role, a.location, a.term, a.next_action, a.notes, a.ats].some((v) => v.toLowerCase().includes(q)))
      : apps
    // blanks sort last in ascending order
    const rank = (a: Application) =>
      sort.key === 'status' ? STATUSES.indexOf(a.status) : (a[sort.key] || '\uffff').toLowerCase()
    return [...filtered].sort((a, b) => {
      const x = rank(a)
      const y = rank(b)
      return (x < y ? -1 : x > y ? 1 : b.id - a.id) * sort.dir
    })
  }, [apps, query, sort])

  const today = todayISO()

  const toggle = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: key === 'applied_date' ? -1 : 1 }))

  return (
    <div className="table-view">
      <input
        type="search"
        className="search"
        placeholder="Search company, role, location, notes…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        aria-label="Search applications"
      />
      <table>
        <thead>
          <tr>
            {COLUMNS.map(([key, label]) => (
              <th key={key} aria-sort={sort.key === key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
                <button type="button" className="th-button" onClick={() => toggle(key)}>
                  {label}
                  <span className="sort-arrow">{sort.key === key ? (sort.dir === 1 ? '▲' : '▼') : ''}</span>
                </button>
              </th>
            ))}
            <th>Links</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => (
            <tr key={a.id} className={a.possibly_ghosted ? 'row--ghost' : undefined}>
              <td>
                {onOpen ? (
                  <button type="button" className="link-button" onClick={() => onOpen(a)}>
                    {a.company}
                  </button>
                ) : (
                  a.company
                )}
              </td>
              <td>{a.role}</td>
              <td>{a.location}</td>
              <td className="nowrap">{a.term}</td>
              <td>
                <select
                  value={a.status}
                  onChange={(e) => onStatus(a.id, e.target.value as Status)}
                  aria-label={`Status for ${a.company}`}
                >
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>{STATUS_LABEL[s]}</option>
                  ))}
                </select>
              </td>
              <td title={`${a.days_since_applied} days ago`} className="nowrap">{formatDate(a.applied_date)}</td>
              <td className={`nowrap${followUpDue(a, today) ? ' due' : ''}`} title={a.next_action || undefined}>
                {a.follow_up_date ? formatDate(a.follow_up_date) : ''}
              </td>
              <td className="muted">{a.ats || a.source}</td>
              <td className="links">
                {a.job_url && <a href={a.job_url} target="_blank" rel="noreferrer">Posting</a>}
                {a.email_url && <a href={a.email_url} target="_blank" rel="noreferrer">Email</a>}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={COLUMNS.length + 1} className="empty">{query ? 'No matches.' : 'No applications yet.'}</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
