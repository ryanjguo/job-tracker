// Typed wrappers around the FastAPI backend (see PLAN.md "API").

export type Status = 'applied' | 'oa' | 'interview' | 'offer' | 'rejected' | 'ghosted' | 'withdrawn'

export const STATUSES: Status[] = ['applied', 'oa', 'interview', 'offer', 'rejected', 'ghosted', 'withdrawn']

export const STATUS_LABEL: Record<Status, string> = {
  applied: 'Applied',
  oa: 'OA',
  interview: 'Interview',
  offer: 'Offer',
  rejected: 'Rejected',
  ghosted: 'Ghosted',
  withdrawn: 'Withdrawn',
}

export interface StatusEvent {
  status: Status
  at: string
}

export interface Application {
  id: number
  company: string
  role: string
  status: Status
  applied_date: string // YYYY-MM-DD
  job_url: string
  notes: string
  source: 'email' | 'review' | 'manual' | 'import'
  ats: string
  created_at: string
  status_changed_at: string
  days_since_applied: number
  possibly_ghosted: boolean
  email_url: string | null
  events: StatusEvent[]
}

export interface ApplicationInput {
  company: string
  role: string
  applied_date: string
  job_url: string
  notes: string
  status: Status
}

export interface Stats {
  total: number
  by_status: Record<Status, number>
  response_rate: number
  median_days_to_response: number | null
  applied_last_7_days: number
  possibly_ghosted: number
  per_week: { week_start: string; count: number }[]
}

export interface Meta {
  imap_configured: boolean
  imap_user: string
  imap_folder: string
  last_sync_at: string | null
  ghost_after_days: number
  statuses: Status[]
  review_count: number
}

export interface EmailRecord {
  id: number
  sender: string
  subject: string
  received_at: string | null
  snippet: string
  guessed_company: string
  guessed_role: string
  ats: string
  outcome: 'created' | 'duplicate' | 'review' | 'accepted' | 'dismissed' | 'ignored'
  reason: string
  application_id: number | null
  email_url: string | null
}

export interface SyncSummary {
  scanned: number
  candidates: number
  created: number
  duplicates: number
  review: number
  ignored: number
  errors: string[]
  since: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new Error("Couldn't reach the API. Is the backend running on :8000?")
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join('; ')
    } catch {
      // not JSON: keep the status line
    }
    throw new Error(detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const api = {
  applications: () => request<Application[]>('/api/applications'),
  createApplication: (body: Partial<ApplicationInput> & { company: string }) =>
    request<Application>('/api/applications', json('POST', body)),
  updateApplication: (id: number, patch: Partial<ApplicationInput>) =>
    request<Application>(`/api/applications/${id}`, json('PATCH', patch)),
  deleteApplication: (id: number) => request<void>(`/api/applications/${id}`, json('DELETE')),
  emails: (outcome: 'review' | 'ignored') => request<EmailRecord[]>(`/api/emails?outcome=${outcome}`),
  acceptEmail: (id: number, body: { company: string; role: string; job_url?: string }) =>
    request<Application>(`/api/emails/${id}/accept`, json('POST', body)),
  dismissEmail: (id: number) => request<void>(`/api/emails/${id}/dismiss`, json('POST')),
  stats: () => request<Stats>('/api/stats'),
  meta: () => request<Meta>('/api/meta'),
  sync: () => request<SyncSummary>('/api/sync', json('POST')),
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}
