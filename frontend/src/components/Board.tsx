import { useState } from 'react'
import { STATUSES, STATUS_LABEL, type Application, type Status } from '../api'
import { AppCard } from './AppCard'

interface Props {
  apps: Application[]
  onStatus: (id: number, status: Status) => void
  onOpen?: (app: Application) => void
}

/** One column per status; drag a card to another column to change its status. */
export function Board({ apps, onStatus, onOpen }: Props) {
  const [over, setOver] = useState<Status | null>(null)

  return (
    <div className="board">
      {STATUSES.map((status) => {
        const cards = apps.filter((a) => a.status === status)
        return (
          <section
            key={status}
            className={`column column--${status}${over === status ? ' column--over' : ''}`}
            aria-label={STATUS_LABEL[status]}
            data-testid={`column-${status}`}
            onDragOver={(e) => {
              e.preventDefault()
              e.dataTransfer.dropEffect = 'move'
              if (over !== status) setOver(status)
            }}
            onDragLeave={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOver(null)
            }}
            onDrop={(e) => {
              e.preventDefault()
              setOver(null)
              const id = Number(e.dataTransfer.getData('text/plain'))
              const app = apps.find((a) => a.id === id)
              if (app && app.status !== status) onStatus(id, status)
            }}
          >
            <h2 className="column__title">
              {STATUS_LABEL[status]} <span className="count">{cards.length}</span>
            </h2>
            <div className="column__cards">
              {cards.map((a) => (
                <AppCard key={a.id} app={a} onStatus={onStatus} onOpen={onOpen} />
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}
