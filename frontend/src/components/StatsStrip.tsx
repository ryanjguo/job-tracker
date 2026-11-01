import type { Stats } from '../api'
import { percent } from '../format'

export function StatsStrip({ stats }: { stats: Stats | null }) {
  const tiles: [string, string, string?][] = stats
    ? [
        ['Total', String(stats.total)],
        ['Applied, last 7 days', String(stats.applied_last_7_days)],
        ['Response rate', percent(stats.response_rate), 'Share that reached OA, interview, offer or rejection'],
        [
          'Median days to response',
          stats.median_days_to_response === null ? '–' : String(stats.median_days_to_response),
        ],
        ['Possibly ghosted', String(stats.possibly_ghosted), 'Still "Applied" after the ghost window'],
      ]
    : []

  return (
    <section className="stats" aria-label="Stats">
      {tiles.map(([label, value, hint]) => (
        <div className="stat" key={label} title={hint}>
          <div className="stat__value">{value}</div>
          <div className="stat__label">{label}</div>
        </div>
      ))}
    </section>
  )
}
