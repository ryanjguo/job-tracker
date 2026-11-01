import { useState } from 'react'
import type { EmailRecord } from '../api'
import { formatDateTime } from '../format'

interface Props {
  email: EmailRecord
  /** "review": form is always open, with Dismiss. "skipped": form opens via "Add as application". */
  mode: 'review' | 'skipped'
  onAccept: (email: EmailRecord, company: string, role: string) => Promise<void>
  onDismiss?: (email: EmailRecord) => Promise<void>
}

export function EmailItem({ email, mode, onAccept, onDismiss }: Props) {
  const [company, setCompany] = useState(email.guessed_company)
  const [role, setRole] = useState(email.guessed_role)
  const [open, setOpen] = useState(mode === 'review')
  const [busy, setBusy] = useState(false)

  const run = async (fn: () => Promise<void>) => {
    setBusy(true)
    try {
      await fn()
    } finally {
      setBusy(false)
    }
  }

  return (
    <article className="email" data-testid={`email-${email.id}`}>
      <div className="email__head">
        <strong className="email__subject">{email.subject || '(no subject)'}</strong>
        {email.received_at && <span className="muted">{formatDateTime(email.received_at)}</span>}
      </div>
      <div className="muted email__sender">
        {email.sender}
        {email.ats && <span className="badge">{email.ats}</span>}
      </div>
      {email.snippet && <p className="email__snippet">{email.snippet}</p>}
      <div className="email__reason muted">
        {mode === 'review' ? 'Why it needs review' : 'Skipped because'}: {email.reason || 'n/a'}
      </div>

      {open ? (
        <form
          className="email__form"
          onSubmit={(e) => {
            e.preventDefault()
            if (company.trim()) void run(() => onAccept(email, company.trim(), role.trim()))
          }}
        >
          <label>
            Company
            <input value={company} onChange={(e) => setCompany(e.target.value)} required maxLength={200} />
          </label>
          <label>
            Role
            <input value={role} onChange={(e) => setRole(e.target.value)} maxLength={300} />
          </label>
          <div className="email__actions">
            <button type="submit" className="primary" disabled={busy || !company.trim()}>
              {mode === 'review' ? 'Accept' : 'Add'}
            </button>
            {mode === 'review' && onDismiss && (
              <button type="button" disabled={busy} onClick={() => void run(() => onDismiss(email))}>
                Dismiss
              </button>
            )}
            {mode === 'skipped' && (
              <button type="button" onClick={() => setOpen(false)}>Cancel</button>
            )}
            {email.email_url && (
              <a href={email.email_url} target="_blank" rel="noreferrer">Open email</a>
            )}
          </div>
        </form>
      ) : (
        <div className="email__actions">
          <button type="button" onClick={() => setOpen(true)}>Add as application</button>
          {email.email_url && (
            <a href={email.email_url} target="_blank" rel="noreferrer">Open email</a>
          )}
        </div>
      )}
    </article>
  )
}
