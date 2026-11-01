import type { Application, Status } from '../api'
import { daysAgo, formatDate } from '../format'

interface Props {
  app: Application
  onStatus: (id: number, status: Status) => void
  onOpen?: (app: Application) => void
}

export function AppCard({ app, onStatus, onOpen }: Props) {
  return (
    <article
      className={`card${app.possibly_ghosted ? ' card--ghost' : ''}${onOpen ? ' card--clickable' : ''}`}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData('text/plain', String(app.id))
        e.dataTransfer.effectAllowed = 'move'
      }}
      onClick={() => onOpen?.(app)}
      data-testid={`card-${app.id}`}
    >
      <div className="card__top">
        <strong className="card__company">{app.company}</strong>
        {app.ats && <span className="badge">{app.ats}</span>}
      </div>
      {app.role && <div className="card__role">{app.role}</div>}
      <div className="card__meta muted" title={app.applied_date}>
        {formatDate(app.applied_date)} · {daysAgo(app.days_since_applied)}
      </div>
      <div className="card__links" onClick={(e) => e.stopPropagation()}>
        {app.job_url && (
          <a href={app.job_url} target="_blank" rel="noreferrer">Posting</a>
        )}
        {app.email_url && (
          <a href={app.email_url} target="_blank" rel="noreferrer">Email</a>
        )}
        {app.possibly_ghosted && (
          <button type="button" className="link-button" onClick={() => onStatus(app.id, 'ghosted')}>
            Mark ghosted
          </button>
        )}
      </div>
    </article>
  )
}
