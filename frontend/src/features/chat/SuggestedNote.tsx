import { Sparkles } from 'lucide-react'
import type { ReactNode } from 'react'
import type { ChatScope, SavedNote } from '@/api/client'
import { useSaveSuggestion } from '@/api/queries'
import { pressable } from '@/components/motion'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { savedNoteHref, suggestionError } from './noteBlocks'

export type SuggestionSave = { scope: ChatScope; outputId: string; saved: SavedNote | undefined }

type Props = {
  index: number
  /** Given once the answer is saved and listed. Absent while it streams, so Save stays disabled. */
  save?: SuggestionSave
  /** The note's text as the answer renders it, citations included. */
  children: ReactNode
}

/**
 * A note the model suggested (D94), on the AI surface inside its answer. Its label, button and refusal are marked
 * `data-chrome`: they aren't part of the answer, so Save as note's offsets skip them (answerSelection.ts).
 */
export function SuggestedNote({ index, save, children }: Props) {
  const saveNote = useSaveSuggestion()
  const problem = saveNote.error ? suggestionError(saveNote.error) : null
  const chatPaperId = save?.scope.kind === 'paper' ? save.scope.id : null
  return (
    <div
      className="suggested-note flex flex-col gap-2 rounded-xl bg-provenance-llm-surface p-3 ring-1 ring-provenance-llm/40"
      data-note-index={index}
    >
      <p data-chrome className="flex items-center gap-1.5 text-xs font-medium text-provenance-llm">
        <Sparkles aria-hidden className="size-3.5" />
        Suggested note
      </p>
      <div className="space-y-2">{children}</div>
      <div data-chrome className="flex items-center justify-end gap-2 text-xs">
        {save?.saved ? (
          <p className="text-muted-foreground">
            Saved ·{' '}
            <a href={savedNoteHref(save.saved, chatPaperId)} className="text-primary hover:underline">
              Open
            </a>
          </p>
        ) : (
          <Button
            variant="outline"
            size="xs"
            className={cn(pressable)}
            disabled={!save || saveNote.isPending}
            onClick={() => save && saveNote.mutate({ scope: save.scope, outputId: save.outputId, index })}
          >
            {saveNote.isPending ? 'Saving…' : 'Save'}
          </Button>
        )}
      </div>
      {problem && (
        <p data-chrome role="alert" className="text-xs text-destructive">
          {problem}
        </p>
      )}
    </div>
  )
}
