import { useCallback, useEffect, useState } from 'react'
import { api, errorMessage, type EmailRecord } from '../api'
import { EmailItem } from './EmailItem'

interface Props {
  /** Called after an email is accepted or dismissed, so the board, stats and badge refresh. */
  onChanged: () => Promise<void>
  onError: (text: string) => void
}

export function ReviewQueue({ onChanged, onError }: Props) {
  const [review, setReview] = useState<EmailRecord[] | null>(null)
  const [skipped, setSkipped] = useState<EmailRecord[] | null>(null)
  const [showSkipped, setShowSkipped] = useState(false)

  const loadReview = useCallback(
    () => api.emails('review').then(setReview, (e) => onError(errorMessage(e))),
    [onError],
  )
  const loadSkipped = useCallback(
    () => api.emails('ignored').then(setSkipped, (e) => onError(errorMessage(e))),
    [onError],
  )

  useEffect(() => {
    void loadReview()
  }, [loadReview])

  useEffect(() => {
    if (showSkipped && skipped === null) void loadSkipped()
  }, [showSkipped, skipped, loadSkipped])

  const accept = async (email: EmailRecord, company: string, role: string) => {
    try {
      await api.acceptEmail(email.id, { company, role })
      setReview((cur) => cur?.filter((r) => r.id !== email.id) ?? null)
      setSkipped((cur) => cur?.filter((r) => r.id !== email.id) ?? null)
      await onChanged()
    } catch (e) {
      onError(`Couldn't add ${company}: ${errorMessage(e)}`)
    }
  }

  const dismiss = async (email: EmailRecord) => {
    try {
      await api.dismissEmail(email.id)
      setReview((cur) => cur?.filter((r) => r.id !== email.id) ?? null)
      await onChanged()
    } catch (e) {
      onError(`Couldn't dismiss: ${errorMessage(e)}`)
    }
  }

  return (
    <div className="review">
      <section>
        <h2 className="section-title">Needs review</h2>
        <p className="muted">
          These look like application confirmations, but the company wasn't found or was only guessed from the sender.
          Check the company and role, then accept.
        </p>
        {review === null ? (
          <p className="muted">Loading…</p>
        ) : review.length === 0 ? (
          <p className="empty">Nothing to review.</p>
        ) : (
          <div className="email-list">
            {review.map((r) => (
              <EmailItem key={r.id} email={r} mode="review" onAccept={accept} onDismiss={dismiss} />
            ))}
          </div>
        )}
      </section>

      <details
        className="skipped"
        open={showSkipped}
        onToggle={(e) => setShowSkipped((e.currentTarget as HTMLDetailsElement).open)}
      >
        <summary>
          Skipped emails{skipped ? ` (${skipped.length})` : ''}
          <span className="muted"> · emails the parser decided weren't new applications</span>
        </summary>
        {skipped === null ? (
          <p className="muted">Loading…</p>
        ) : skipped.length === 0 ? (
          <p className="empty">No skipped emails.</p>
        ) : (
          <div className="email-list">
            {skipped.map((r) => (
              <EmailItem key={r.id} email={r} mode="skipped" onAccept={accept} />
            ))}
          </div>
        )}
      </details>
    </div>
  )
}
