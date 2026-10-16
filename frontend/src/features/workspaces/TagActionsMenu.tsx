import { MoreHorizontal } from 'lucide-react'
import { useRef, useState } from 'react'
import { useDeleteTag, useRenameTag } from '@/api/queries'
import type { TagSummary } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { plural } from '@/features/charts/chartMeta'
import { tagErrorText } from './tagErrors'

type Props = {
  workspaceId: string
  tag: TagSummary
  onRenamed: (oldName: string, newName: string) => void
  onDeleted: (name: string) => void
  /** Where focus goes once the tag is deleted and its trigger is gone. */
  focusAfterDelete?: () => void
}

/** The "…" menu of a tag: rename it in a dialog, or delete it after a confirmation. */
export function TagActionsMenu({ workspaceId, tag, onRenamed, onDeleted, focusAfterDelete }: Props) {
  const [dialog, setDialog] = useState<'rename' | 'delete' | null>(null)
  const [name, setName] = useState(tag.name)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const deleted = useRef(false)
  const rename = useRenameTag(workspaceId)
  const del = useDeleteTag(workspaceId)

  function close() {
    setDialog(null)
    rename.reset()
    del.reset()
  }

  // The dialogs open from a menu item, not a trigger of their own, so Radix would hand focus to the body.
  const returnFocus = (event: Event) => {
    event.preventDefault()
    // After a delete the trigger is gone, so focus goes where the parent says.
    if (deleted.current) focusAfterDelete?.()
    else triggerRef.current?.focus()
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button ref={triggerRef} variant="ghost" size="icon-sm" aria-label={`Actions for tag ${tag.name}`}>
            <MoreHorizontal aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => { setName(tag.name); setDialog('rename') }}>Rename</DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setDialog('delete')}>Delete</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={dialog === 'rename'} onOpenChange={(next) => !next && close()}>
        <DialogContent onCloseAutoFocus={returnFocus}>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              rename.mutate({ tagId: tag.id, newName: name }, { onSuccess: (done) => { close(); onRenamed(tag.name, done.new) } })
            }}
          >
            <DialogHeader>
              <DialogTitle>Rename tag</DialogTitle>
              <DialogDescription className="sr-only">Give the tag a new name.</DialogDescription>
            </DialogHeader>
            <Input aria-label="Tag name" value={name} onChange={(event) => setName(event.target.value)} autoFocus />
            {rename.error && <p role="alert" className="text-sm text-destructive">{tagErrorText(rename.error.message)}</p>}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={close}>Cancel</Button>
              <Button type="submit" disabled={rename.isPending}>Save</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={dialog === 'delete'} onOpenChange={(next) => !next && close()}>
        <DialogContent onCloseAutoFocus={returnFocus}>
          <DialogHeader>
            <DialogTitle>Delete tag "{tag.name}"?</DialogTitle>
            <DialogDescription>The tag is removed from {plural(tag.papers, 'paper')}. No papers are deleted.</DialogDescription>
          </DialogHeader>
          {del.error && <p role="alert" className="text-sm text-destructive">{tagErrorText(del.error.message)}</p>}
          <DialogFooter>
            <Button variant="outline" onClick={close}>Cancel</Button>
            <Button variant="destructive" disabled={del.isPending} onClick={() => del.mutate(tag.id, { onSuccess: () => { deleted.current = true; close(); onDeleted(tag.name) } })}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
