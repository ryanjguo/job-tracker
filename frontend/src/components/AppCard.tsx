import { followUpDue, type Application, type Status } from '../api'
import { daysAgo, formatDate, todayISO } from '../format'

interface Props {
  app: Application
  onStatus: (id: number, status: Status) => void
  onOpen?: (app: Application) => void
}

export function AppCard({ app, onStatus, onOpen }: Props) {
  const place = [app.location, app.term].filter(Boolean).join(' · ')
  const due = followUpDue(app, todayISO())
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
        {onOpen ? (
          // The real control for keyboard / screen-reader users; a mouse click anywhere on the
          // card does the same. Not the whole card, so the links inside stay separate controls.
          <button
            type="button"
            className="card__company card__open"
            onClick={(e) => {
              e.stopPropagation()
              onOpen(app)
            }}
            aria-label={`Edit ${app.company}${app.role ? `, ${app.role}` : ''}`}
          >
            {app.company}
          </button>
        ) : (
          <strong className="card__company">{app.company}</strong>
        )}
        {app.ats && <span className="badge">{app.ats}</span>}
      </div>
      {app.role && <div className="card__role">{app.role}</div>}
      {place && <div className="card__place muted">{place}</div>}
      <div className="card__meta muted" title={app.applied_date}>
        {formatDate(app.applied_date)} · {daysAgo(app.days_since_applied)}
      </div>
      {(app.next_action || app.follow_up_date) && (
        <div className={`card__next${due ? ' card__next--due' : ''}`}>
          {app.next_action || 'Follow up'}
          {app.follow_up_date && <> · {due ? 'due ' : 'by '}{formatDate(app.follow_up_date)}</>}
        </div>
      )}
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
