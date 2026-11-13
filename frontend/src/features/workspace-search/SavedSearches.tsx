import { useState } from 'react'
import { useDeleteSavedSearch, useMarkSavedSearchSeen, useRunSavedSearchNow, useSavedSearches, useUpdateSavedSearch, type SavedSearchInbox } from '@/api/queries'
import type { SavedSearch } from '@/api/client'
import { glass } from '@/components/glass'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { SavedSearchDialog } from './SavedSearchDialog'
import { READ_ONLY_TEXT } from '@/lib/errorWords'
import { useReadOnlyWorkspace } from '../workspaces/readOnlyContext'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { describeSchedule, describeYears, errorText, relative } from './schedule'

const localTime = (iso: string) => new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })

type Editing = SavedSearch | 'new' | null

/** The workspace's saved (scheduled) searches, under the Start bar. */
export function SavedSearches({
  workspaceId,
  currentQuery,
  onRunStarted,
  onShowNew,
}: {
  workspaceId: string
  currentQuery: string
  onRunStarted: (runId: string) => void
  /** Opens a saved search's new finds in the result list; the card then marks them seen. */
  onShowNew: (inbox: SavedSearchInbox) => void
}) {
  const list = useSavedSearches(workspaceId)
  const update = useUpdateSavedSearch(workspaceId)
  const remove = useDeleteSavedSearch(workspaceId)
  const runNow = useRunSavedSearchNow(workspaceId)
  const markSeen = useMarkSavedSearchSeen(workspaceId)
  const readOnly = useReadOnlyWorkspace()
  const [editing, setEditing] = useState<Editing>(null)
  const [deleting, setDeleting] = useState<SavedSearch | null>(null)
  const rows = list.data ?? []
  const actionError = errorText((runNow.error ?? update.error ?? remove.error)?.message)
  // Keep the last name while the dialog fades out, so its text does not blank mid-animation.
  const [lastDeleting, setLastDeleting] = useState<SavedSearch | null>(null)

  return (
    <section aria-label="Saved searches" className="grid gap-2 border-b px-3 py-2 text-sm">
      <div className="flex items-center justify-between">
        <h2 className="font-medium">Saved searches</h2>
        <Button variant="ghost" size="sm" disabled={readOnly} title={readOnly ? READ_ONLY_TEXT : undefined} onClick={() => setEditing('new')}>Save this search…</Button>
      </div>
      {actionError && (
        <Alert variant="destructive">
          <AlertDescription>{actionError}</AlertDescription>
        </Alert>
      )}
      {rows.length === 0 && !list.isPending && (
        <p className="text-sm text-muted-foreground">None yet. Save a search to rerun it on a schedule.</p>
      )}
      {rows.map((s) => (
        <div key={s.id} className="grid gap-0.5 rounded-md border px-3 py-2">
          <div className="flex items-center gap-2">
            <span className="min-w-0 flex-1 truncate font-medium">{s.query}</span>
            {s.new_hits > 0 && (
              <Button variant="secondary" size="sm" aria-label={`${s.new_hits} new from ${s.query}`}
                onClick={() => { onShowNew({ savedSearchId: s.id, query: s.query, since: s.seen_at }); markSeen.mutate(s.id) }}>
                {s.new_hits} new
              </Button>
            )}
            <Switch size="sm" checked={s.enabled} aria-label={`Enabled: ${s.query}`}
              onCheckedChange={(enabled) => update.mutate({ id: s.id, body: { enabled } })} />
            <Button variant="ghost" size="sm" aria-label={`Run now: ${s.query}`} disabled={readOnly || runNow.isPending} title={readOnly ? READ_ONLY_TEXT : undefined} onClick={() => runNow.mutate(s.id, { onSuccess: (r) => onRunStarted(r.id) })}>
              Run now
            </Button>
            <Button variant="ghost" size="sm" aria-label={`Edit: ${s.query}`} disabled={readOnly} title={readOnly ? READ_ONLY_TEXT : undefined} onClick={() => setEditing(s)}>Edit</Button>
            <Button variant="ghost" size="sm" aria-label={`Delete: ${s.query}`} disabled={readOnly} title={readOnly ? READ_ONLY_TEXT : undefined} onClick={() => { setDeleting(s); setLastDeleting(s) }}>Delete</Button>
          </div>
          <p className="text-xs text-muted-foreground">
            {[
              describeSchedule(s),
              s.sources.length ? `${s.sources.length} sources` : 'all sources',
              describeYears(s.year_from, s.year_to),
            ].filter(Boolean).join(' · ')}
          </p>
          <p className="text-xs text-muted-foreground">
            Last run: {s.last_run_at ? `${relative(s.last_run_at)}${s.last_run_status ? ` (${s.last_run_status})` : ''}` : 'never'}
            {' · '}
            <span>{s.enabled && s.next_run_at ? `Next run: ${localTime(s.next_run_at)}` : 'Paused'}</span>
          </p>
          {s.last_error && <p className="text-xs text-muted-foreground">{s.last_error}</p>}
        </div>
      ))}

      {editing && (
        <SavedSearchDialog
          workspaceId={workspaceId}
          saved={editing === 'new' ? null : editing}
          initialQuery={currentQuery}
          onClose={() => setEditing(null)}
        />
      )}
      <Dialog open={deleting !== null} onOpenChange={(open) => !open && setDeleting(null)}>
        <DialogContent className={cn(glass, 'bg-glass-strong ring-glass-border sm:max-w-sm')}>
          <DialogHeader>
            <DialogTitle>Delete saved search?</DialogTitle>
            <DialogDescription>
              “{lastDeleting?.query}” will stop running. Papers it already found stay where they are.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="bg-transparent">
            <Button variant="outline" onClick={() => setDeleting(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => { remove.mutate(deleting!.id); setDeleting(null) }}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}
