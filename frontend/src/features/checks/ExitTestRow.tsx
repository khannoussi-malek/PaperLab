import { Button } from '@/components/ui/button'
import { useNotes } from '@/api/queries'
import type { Pass } from '@/features/reading/passes'
import { exitTestLine, exitTestNote, exitTestStatus } from './exitTest'
import { usePaperChecks } from './queries'

type Props = { paperId: string; pass: Pass; onWrite: (kind: Pass['noteKind']) => void; onOpen: (noteId: string) => void }

/** One pass's exit test: whether the reader has written it and what its check found (D118: counts only). */
export function ExitTestRow({ paperId, pass, onWrite, onOpen }: Props) {
  const notes = useNotes(paperId)
  const checks = usePaperChecks(paperId)
  const note = exitTestNote(notes.data ?? [], pass.noteKind)
  const status = exitTestStatus(note, note && checks.data?.find((check) => check.note_id === note.id))
  const { text, action } = exitTestLine(pass.noteKind, status)
  return (
    <div className="mt-1.5 flex items-center justify-between gap-2 text-sm">
      <p>{text}</p>
      <Button variant="ghost" size="sm" onClick={() => (action === 'write' || !note ? onWrite(pass.noteKind) : onOpen(note.id))}>
        {action === 'write' ? 'Write it' : 'Open'}
      </Button>
    </div>
  )
}
