import type { Application } from './api'

/** Search + term filter shared by the Board and the Table. */
export interface Filters {
  query: string
  term: string // '' = all terms
}

export const NO_FILTERS: Filters = { query: '', term: '' }

export function isFiltering(f: Filters): boolean {
  return f.query.trim() !== '' || f.term !== ''
}

export function applyFilters(apps: Application[], f: Filters): Application[] {
  const q = f.query.trim().toLowerCase()
  return apps.filter(
    (a) =>
      (!f.term || a.term === f.term) &&
      (!q || [a.company, a.role, a.location, a.term, a.next_action, a.notes, a.ats].some((v) => v.toLowerCase().includes(q))),
  )
}

/** Distinct terms in the data, e.g. ["Fall 2026", "Summer 2027"]. */
export function termsOf(apps: Application[]): string[] {
  return [...new Set(apps.map((a) => a.term).filter(Boolean))].sort((a, b) => a.localeCompare(b))
}
