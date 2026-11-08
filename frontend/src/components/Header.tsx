import type { ReactNode } from 'react'
import type { Meta } from '../api'
import { interval, timeAgo } from '../format'

interface Props {
  meta: Meta | null
  syncing: boolean
  onSync: () => void
  children?: ReactNode // extra actions (e.g. "+ Add")
}

export function Header({ meta, syncing, onSync, children }: Props) {
  let syncText = ''
  if (meta) {
    if (!meta.imap_configured) syncText = 'IMAP not configured (see backend/.env)'
    else {
      syncText = meta.last_sync_at ? `Last synced ${timeAgo(meta.last_sync_at)}` : 'Never synced'
      if (meta.sync_every_minutes > 0) syncText += ` · auto every ${interval(meta.sync_every_minutes)}`
    }
  }

  return (
    <header className="header">
      <h1>Job Tracker</h1>
      <div className="header__actions">
        <span className="muted" title={meta?.last_sync_at ?? undefined}>{syncText}</span>
        {meta?.last_sync_error && (
          <span className="sync-error" role="alert" title={meta.last_sync_error}>
            Last sync failed: {meta.last_sync_error}
          </span>
        )}
        <button type="button" onClick={onSync} disabled={syncing}>
          {syncing ? 'Syncing…' : 'Sync now'}
        </button>
        {children}
      </div>
    </header>
  )
}
