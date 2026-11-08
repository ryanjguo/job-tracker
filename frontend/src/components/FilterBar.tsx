import { isFiltering, NO_FILTERS, type Filters } from '../filters'

interface Props {
  filters: Filters
  onChange: (f: Filters) => void
  terms: string[]
  shown: number
  total: number
}

export function FilterBar({ filters, onChange, terms, shown, total }: Props) {
  const active = isFiltering(filters)
  return (
    <div className="filter-bar" role="search">
      <input
        type="search"
        className="search"
        placeholder="Search company, role, location, notes…"
        value={filters.query}
        onChange={(e) => onChange({ ...filters, query: e.target.value })}
        aria-label="Search applications"
      />
      {terms.length > 0 && (
        <select
          value={filters.term}
          onChange={(e) => onChange({ ...filters, term: e.target.value })}
          aria-label="Filter by term"
        >
          <option value="">All terms</option>
          {terms.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      )}
      {active && (
        <>
          <span className="muted" aria-live="polite">
            {shown} of {total}
          </span>
          <button type="button" className="link-button" onClick={() => onChange(NO_FILTERS)}>
            Clear
          </button>
        </>
      )}
    </div>
  )
}
