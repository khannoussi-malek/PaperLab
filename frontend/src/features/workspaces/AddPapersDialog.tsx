import { useState } from 'react'
import { usePapers, useWorkspaceMembership } from '@/api/queries'
import { glass } from '@/components/glass'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { byline } from '@/features/library/paperMeta'
import { cn } from '@/lib/utils'

type Props = {
  workspaceId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** A searchable checklist of library papers not yet in the workspace. */
export function AddPapersDialog({ workspaceId, open, onOpenChange }: Props) {
  const papers = usePapers()
  const membership = useWorkspaceMembership()
  const [selected, setSelected] = useState<string[]>([])
  const candidates = (papers.data ?? []).filter((paper) => !paper.workspace_ids.includes(workspaceId))

  function close() {
    setSelected([])
    membership.reset()
    onOpenChange(false)
  }

  function toggle(paperId: string) {
    setSelected((ids) => (ids.includes(paperId) ? ids.filter((id) => id !== paperId) : [...ids, paperId]))
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <DialogContent className={cn(glass, 'bg-glass-strong ring-glass-border sm:max-w-lg')}>
        <DialogHeader>
          <DialogTitle>Add papers</DialogTitle>
          <DialogDescription>A paper can be in several workspaces. Removing it later keeps it in your library.</DialogDescription>
        </DialogHeader>
        <Command className="bg-transparent p-0">
          <CommandInput aria-label="Search papers" placeholder="Search your library…" />
          <CommandList>
            <CommandEmpty>
              {candidates.length === 0 ? 'Every library paper is already in this workspace.' : 'No matching papers.'}
            </CommandEmpty>
            {candidates.map((paper) => {
              const checked = selected.includes(paper.id)
              return (
                <CommandItem
                  key={paper.id}
                  // The id keeps two papers with the same title apart; the filter searches the keywords.
                  value={paper.id}
                  keywords={[paper.title, byline(paper)]}
                  data-paper-id={paper.id}
                  data-checked={checked}
                  aria-checked={checked}
                  onSelect={() => toggle(paper.id)}
                >
                  <span className="min-w-0 flex-1 truncate" title={paper.title}>
                    {paper.title}
                  </span>
                </CommandItem>
              )
            })}
          </CommandList>
        </Command>
        {membership.error && (
          <Alert variant="destructive" className="border-glass-border">
            <AlertDescription>{membership.error.message}</AlertDescription>
          </Alert>
        )}
        <DialogFooter className="bg-transparent">
          <Button variant="outline" onClick={close}>
            Cancel
          </Button>
          <Button
            disabled={selected.length === 0 || membership.isPending}
            onClick={() => membership.mutate({ workspaceId, paperIds: selected, member: true }, { onSuccess: close })}
          >
            {selected.length === 1 ? 'Add 1 paper' : `Add ${selected.length} papers`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
