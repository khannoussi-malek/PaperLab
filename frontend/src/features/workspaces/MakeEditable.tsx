import { useState } from 'react'
import type { Workspace } from '@/api/client'
import { useMakeWorkspaceEditable } from '@/api/queries'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { codeInWords } from '@/lib/errorWords'

export const READ_ONLY_BANNER = 'Imported read-only. Make it editable to change its papers, tags, criteria or searches.'

/** The banner of an imported workspace, with Make it editable behind a confirmation. Renders nothing once editable. */
export function MakeEditableBanner({ workspace }: { workspace: Workspace }) {
  const [open, setOpen] = useState(false)
  const makeEditable = useMakeWorkspaceEditable()
  if (!workspace.read_only) return null
  return (
    <Alert>
      <AlertDescription className="flex flex-wrap items-center gap-2">
        <span>{READ_ONLY_BANNER}</span>
        <Button size="sm" onClick={() => setOpen(true)}>Make it editable</Button>
      </AlertDescription>
      {makeEditable.error && <p role="alert" className="text-sm text-destructive">{codeInWords(makeEditable.error.message)}</p>}
      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Make this workspace editable?</AlertDialogTitle>
            <AlertDialogDescription>It stays editable.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => makeEditable.mutate(workspace.id)}>Make editable</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Alert>
  )
}
