import { Sparkles } from 'lucide-react'
import { useState } from 'react'
import type { NoteSuggestion } from '@/api/client'
import { usePromoteNote, useSuggestNotes } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter } from '@/components/ui/card'

type Props = {
  paperId: string
  /** False for a paper saved without its PDF: suggestions are spots on its pages, and it has none. */
  hasPdf?: boolean
}

/** "Suggest notes": generates a handful of cited note candidates and shows each as a card the reader accepts or
 * dismisses individually — notes are never saved automatically (chat.py's own docstring states the same rule
 * for chat: an answer becomes a note only through an explicit human choice; this is a different starting point
 * for that choice, not an exception to it). Accepting one goes through the unchanged POST /api/notes/promote —
 * the same endpoint a chat answer's own text selection already uses — so there's no separate "accept" write path
 * to keep in sync. */
export function SuggestedNotes({ paperId, hasPdf = true }: Props) {
  const suggest = useSuggestNotes(paperId)
  const promote = usePromoteNote()
  const [outputId, setOutputId] = useState<string | null>(null)
  const [pending, setPending] = useState<NoteSuggestion[]>([])
  const [acceptingIndex, setAcceptingIndex] = useState<number | null>(null)

  function onSuggest() {
    suggest.mutate(undefined, {
      onSuccess: (result) => {
        setOutputId(result.output_id)
        setPending(result.suggestions)
      },
    })
  }

  function dismiss(index: number) {
    setPending((current) => current.filter((_, i) => i !== index))
  }

  function accept(index: number) {
    if (!outputId) return
    setAcceptingIndex(index)
    promote.mutate(
      { output_id: outputId, body: pending[index].body, chunk_ids: [pending[index].chunk_id] },
      { onSuccess: () => dismiss(index), onSettled: () => setAcceptingIndex(null) },
    )
  }

  // The server's 409 no_pdf, for a click made before the paper had loaded, reads the same as knowing it up front.
  if (!hasPdf || suggest.error?.message === 'no_pdf') {
    return <p className="text-xs text-muted-foreground">Suggested notes need the full text, and this paper has no PDF yet.</p>
  }

  return (
    <div className="flex flex-col gap-2">
      <Button type="button" size="sm" variant="outline" disabled={suggest.isPending} onClick={onSuggest}>
        <Sparkles aria-hidden />
        {suggest.isPending ? 'Suggesting…' : 'Suggest notes'}
      </Button>
      {suggest.isError && (
        <p role="alert" className="text-xs text-destructive">
          {suggest.error.message}
        </p>
      )}
      {promote.isError && (
        <p role="alert" className="text-xs text-destructive">
          {promote.error.message}
        </p>
      )}
      {suggest.isSuccess && pending.length === 0 && (
        <p role="status" className="text-xs text-muted-foreground">
          Nothing stood out enough to suggest — try again, or add notes yourself as you read.
        </p>
      )}
      {pending.map((suggestion, index) => (
        <Card key={`${suggestion.chunk_id}-${index}`} size="sm">
          <CardContent>{suggestion.body}</CardContent>
          <CardFooter className="gap-2">
            <Button type="button" size="sm" disabled={acceptingIndex === index} onClick={() => accept(index)}>
              {acceptingIndex === index ? 'Saving…' : 'Accept'}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => dismiss(index)}>
              Dismiss
            </Button>
          </CardFooter>
        </Card>
      ))}
    </div>
  )
}
