import { useEffect, useRef, useState } from 'react'
import { STATUSES, STATUS_LABEL, type Application, type ApplicationInput, type Status } from '../api'
import { formatDateTime, todayISO } from '../format'

interface Props {
  /** null = add a new application */
  app: Application | null
  onSave: (input: ApplicationInput) => Promise<void>
  onDelete?: () => Promise<void>
  onClose: () => void
}

export function ApplicationModal({ app, onSave, onDelete, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  const [form, setForm] = useState<ApplicationInput>(() => ({
    company: app?.company ?? '',
    role: app?.role ?? '',
    applied_date: app?.applied_date ?? todayISO(),
    job_url: app?.job_url ?? '',
    notes: app?.notes ?? '',
    status: app?.status ?? 'applied',
  }))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const dialog = ref.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])

  const set = <K extends keyof ApplicationInput>(key: K, value: ApplicationInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const run = async (fn: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setBusy(false)
    }
  }

  return (
    <dialog
      ref={ref}
      className="modal"
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) ref.current.close() // click on the backdrop
      }}
      aria-labelledby="modal-title"
    >
      <form
        method="dialog"
        onSubmit={(e) => {
          e.preventDefault()
          void run(() => onSave({ ...form, company: form.company.trim() }))
        }}
      >
        <h2 id="modal-title">{app ? 'Edit application' : 'Add application'}</h2>

        <div className="form-grid">
          <label>
            Company
            <input
              value={form.company}
              onChange={(e) => set('company', e.target.value)}
              required
              maxLength={200}
              autoFocus
            />
          </label>
          <label>
            Role
            <input value={form.role} onChange={(e) => set('role', e.target.value)} maxLength={300} />
          </label>
          <label>
            Applied
            <input
              type="date"
              value={form.applied_date}
              onChange={(e) => set('applied_date', e.target.value)}
              required
            />
          </label>
          <label>
            Status
            <select value={form.status} onChange={(e) => set('status', e.target.value as Status)}>
              {STATUSES.map((s) => (
                <option key={s} value={s}>{STATUS_LABEL[s]}</option>
              ))}
            </select>
          </label>
          <label className="span-2">
            Job posting URL
            <input
              type="url"
              value={form.job_url}
              onChange={(e) => set('job_url', e.target.value)}
              maxLength={1000}
              placeholder="https://"
            />
          </label>
          <label className="span-2">
            Notes
            <textarea value={form.notes} onChange={(e) => set('notes', e.target.value)} rows={4} />
          </label>
        </div>

        {app && app.events.length > 0 && (
          <div className="history muted">
            History:{' '}
            {app.events.map((ev, i) => (
              <span key={i}>
                {i > 0 && ' → '}
                {STATUS_LABEL[ev.status]} <span title={ev.at}>({formatDateTime(ev.at)})</span>
              </span>
            ))}
            {app.source !== 'manual' && <> · added from {app.source === 'email' ? 'email' : 'review queue'}</>}
          </div>
        )}

        {error && <p className="form-error" role="alert">{error}</p>}

        <div className="modal__actions">
          {app && onDelete && (
            <button
              type="button"
              className="danger"
              disabled={busy}
              onClick={() => {
                const note = app.source === 'manual' ? '' : " Its emails won't be re-imported on the next sync."
                if (window.confirm(`Delete ${app.company}?${note}`)) void run(onDelete)
              }}
            >
              Delete
            </button>
          )}
          <span className="spacer" />
          <button type="button" onClick={() => ref.current?.close()} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="primary" disabled={busy || !form.company.trim()}>
            {app ? 'Save' : 'Add'}
          </button>
        </div>
      </form>
    </dialog>
  )
}
