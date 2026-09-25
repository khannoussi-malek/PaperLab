import { useState } from 'react'
import type { Note } from '@/api/client'
import { usePapers, useSetNotePapers } from '@/api/queries'
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
import { cn } from '@/lib/utils'
import { unlinkWarnings } from './notePapers'

type Props = {
  note: Note
  onClose: () => void
  /** Told the saved note, e.g. so the reader can say it left this paper. */
  onSaved?: (note: Note) => void
}

/** The note's papers as a searchable checklist of the library (D95). Save sends the whole list; Cancel changes nothing.
 * Mounted only while open, so it always starts from the note's own papers. */
export function EditPapersDialog({ note, onClose, onSaved }: Props) {
  const papers = usePapers()
  const setPapers = useSetNotePapers()
  const [ticked, setTicked] = useState<string[]>(note.paper_ids)
  const warnings = unlinkWarnings(note, papers.data ?? [], ticked)

  function toggle(paperId: string) {
    setTicked((ids) => (ids.includes(paperId) ? ids.filter((id) => id !== paperId) : [...ids, paperId]))
  }

  async function save() {
    try {
      // mutateAsync, not mutate's callbacks: in the reader the card (and this dialog) unmounts once the note leaves
      // the paper's list, and a per-call callback would then never run.
      const saved = await setPapers.mutateAsync({ noteId: note.id, paperIds: ticked })
      onSaved?.(saved)
      onClose()
    } catch {
      // setPapers.error shows under the list, and the dialog stays open to try again.
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className={cn(glass, 'bg-glass-strong ring-glass-border sm:max-w-lg')}>
        <DialogHeader>
          <DialogTitle>Papers</DialogTitle>
          <DialogDescription>Tick the papers this note belongs to. A note can have none.</DialogDescription>
        </DialogHeader>
        <Command className="bg-transparent p-0">
          <CommandInput aria-label="Search papers" placeholder="Search your library…" />
          <CommandList>
            <CommandEmpty>
              {papers.isPending
                ? 'Loading your library…'
                : papers.isError
                  ? "Couldn't load your library."
                  : 'No matching papers.'}
            </CommandEmpty>
            {(papers.data ?? []).map((paper) => {
              const checked = ticked.includes(paper.id)
              return (
                <CommandItem
                  key={paper.id}
                  // The id keeps two papers with the same title apart; the filter searches the keywords.
                  value={paper.id}
                  keywords={[paper.title, ...(paper.year ? [String(paper.year)] : [])]}
                  data-paper-id={paper.id}
                  data-checked={checked}
                  aria-checked={checked}
                  onSelect={() => toggle(paper.id)}
                >
                  <span className="min-w-0 flex-1 truncate" title={paper.title}>
                    {paper.title}
                  </span>
                  {paper.year && <span className="text-xs text-muted-foreground tabular-nums">{paper.year}</span>}
                </CommandItem>
              )
            })}
          </CommandList>
        </Command>
        {warnings.length > 0 && (
          <Alert className="unlink-warning border-glass-border">
            <AlertDescription>
              {warnings.map((warning) => (
                <p key={warning}>{warning}</p>
              ))}
            </AlertDescription>
          </Alert>
        )}
        {setPapers.error && (
          <Alert variant="destructive" className="border-glass-border">
            <AlertDescription>{setPapers.error.message}</AlertDescription>
          </Alert>
        )}
        <DialogFooter className="bg-transparent">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={setPapers.isPending} onClick={() => void save()}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
