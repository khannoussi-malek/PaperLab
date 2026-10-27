import { useState } from 'react'
import type { Manuscript } from '@/api/client'
import { useDeleteManuscript, useUpdateManuscript, useWorkspaces } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { manuscriptFailure } from './errors'

const SELECT_CLASS =
  'h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-xs focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none'
const NONE = '' // the <select> value for "no workspace"

type Props = { manuscript: Manuscript; open: boolean; onOpenChange: (open: boolean) => void }

/** Moves a manuscript to another workspace, or out of every workspace. */
export function MoveManuscriptDialog({ manuscript, open, onOpenChange }: Props) {
  const workspaces = useWorkspaces()
  const update = useUpdateManuscript()
  const [picked, setPicked] = useState<string | null>(null)
  const target = picked ?? manuscript.workspace_id ?? NONE
  const close = (next: boolean) => { setPicked(null); update.reset(); onOpenChange(next) }

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    update.mutate({ id: manuscript.id, patch: { workspace_id: target || null } }, { onSuccess: () => close(false) })
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>Move “{manuscript.title}”</DialogTitle>
            <DialogDescription>Its citations come from the papers of the workspace it is in.</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor="manuscript-workspace">Workspace</Label>
            <select id="manuscript-workspace" className={SELECT_CLASS} value={target} onChange={(e) => setPicked(e.target.value)}>
              <option value={NONE}>No workspace</option>
              {workspaces.data?.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </div>
          {(workspaces.error ?? update.error) && (
            <Alert variant="destructive"><AlertDescription>{manuscriptFailure((workspaces.error ?? update.error)!)}</AlertDescription></Alert>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => close(false)}>Cancel</Button>
            <Button type="submit" disabled={update.isPending || target === (manuscript.workspace_id ?? NONE)}>
              {update.isPending ? 'Moving…' : 'Move'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** Asks, here in the app, before deleting a manuscript with its files, history and PDF. */
export function DeleteManuscriptDialog({ manuscript, open, onOpenChange, onDeleted }: Props & { onDeleted?: () => void }) {
  const remove = useDeleteManuscript()
  const close = (next: boolean) => { remove.reset(); onOpenChange(next) }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete “{manuscript.title}”?</DialogTitle>
          <DialogDescription>Its files, its history and its PDF are deleted too. This can't be undone.</DialogDescription>
        </DialogHeader>
        {remove.error && <Alert variant="destructive"><AlertDescription>{manuscriptFailure(remove.error)}</AlertDescription></Alert>}
        <DialogFooter>
          <Button variant="outline" onClick={() => close(false)}>Cancel</Button>
          <Button
            variant="destructive"
            disabled={remove.isPending}
            onClick={() => remove.mutate(manuscript.id, { onSuccess: () => { close(false); onDeleted?.() } })}
          >
            {remove.isPending ? 'Deleting…' : 'Delete manuscript'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
