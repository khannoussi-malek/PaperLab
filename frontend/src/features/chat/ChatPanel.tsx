import { useEffect, useRef, useState, type CSSProperties } from 'react'
import type { ChatSource, Note, ChatAnswer as SavedAnswer } from '@/api/client'
import { useChatHistory, usePromoteNote, useReindexPaper } from '@/api/queries'
import { Alert, AlertAction, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { readAnswerSelection } from './answerSelection'
import { ChatAnswer } from './ChatAnswer'
import { splitCitations } from './citations'
import { promoteSelection, type PromoteDraft } from './promote'
import { SaveAsNoteButton } from './SaveAsNoteButton'
import { useChatStream, type ChatProblem } from './useChatStream'

const MAX_QUESTION = 2000 // the API's limit (spec §3.10)
// ponytail: a fixed width keeps the floating button inside the panel; measure it if the label ever changes.
const SAVE_BUTTON_WIDTH = 140

/** Labels whose chunk still exists; markers for any other label render as plain text. */
const knownLabels = (answer: SavedAnswer) => new Set(answer.sources.flatMap((source) => (source ? [source.label] : [])))

/** A readable reason a promote failed. The API's own codes aren't meant for display. */
function promoteErrorMessage(message: string): string {
  return message === 'body_not_in_output'
    ? "This selection doesn't match the saved answer. Select the text again."
    : "Couldn't save the note. Try again."
}

type Props = {
  paperId: string
  onCite: (source: ChatSource) => void
  /** Called with the new note once it is saved and listed. */
  onPromoted: (note: Note) => void
}

type Promote = { outputId: string; draft: PromoteDraft; style: CSSProperties }

export function ChatPanel({ paperId, onCite, onPromoted }: Props) {
  const history = useChatHistory(paperId)
  const { stream, ask, retry } = useChatStream(paperId)
  const [question, setQuestion] = useState('')
  const [promote, setPromote] = useState<Promote | null>(null)
  const [promoteError, setPromoteError] = useState<string | null>(null)
  const promoteNote = usePromoteNote(paperId)
  const rootRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const wasBusy = useRef(false)
  const answers = history.data ?? []
  const busy = stream.status === 'sources' || stream.status === 'streaming'
  // A saved answer comes back in the history, so the live copy hides instead of showing twice.
  const showLive = stream.status !== 'idle' && !answers.some((answer) => answer.id === stream.done?.output_id)

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [answers.length, stream.status])

  // Enter disables the Textarea while busy, so the browser blurs it to <body>; bring focus back once it clears.
  useEffect(() => {
    if (wasBusy.current && !busy) textareaRef.current?.focus()
    wasBusy.current = busy
  }, [busy])

  function captureSelection() {
    setPromoteError(null) // a changed selection retires any error about the old one
    const selected = readAnswerSelection()
    const answer = answers.find((a) => a.id === selected?.outputId)
    const draft = selected && answer && promoteSelection(answer.content, answer.sources, selected.anchor, selected.focus)
    const box = rootRef.current?.getBoundingClientRect()
    if (!selected || !draft || !box) return setPromote(null)
    const left = Math.max(8, Math.min(selected.rect.left - box.left, box.width - SAVE_BUTTON_WIDTH))
    setPromote({ outputId: selected.outputId, draft, style: { left, top: selected.rect.bottom - box.top + 6 } })
  }

  // The selection can change without a mouseup: dragging still fires this repeatedly, and so does
  // Shift+Arrow. Re-running the full capture (not just hiding on collapse) keeps the draft live, not stale.
  useEffect(() => {
    document.addEventListener('selectionchange', captureSelection)
    return () => document.removeEventListener('selectionchange', captureSelection)
  })

  async function saveAsNote() {
    if (!promote) return
    const { outputId, draft } = promote
    try {
      const note = await promoteNote.mutateAsync({ output_id: outputId, body: draft.body, chunk_ids: draft.chunkIds })
      setPromote(null)
      window.getSelection()?.removeAllRanges()
      onPromoted(note)
    } catch (e) {
      // The button (and selection) stay up: the message sits right next to it, and the user can retry.
      setPromoteError(promoteErrorMessage(e instanceof Error ? e.message : String(e)))
    }
  }

  function submit() {
    const text = question.trim()
    if (!text || busy) return
    setQuestion('')
    void ask(text)
  }

  return (
    <div ref={rootRef} className="relative flex min-h-0 flex-1 flex-col">
      <div
        ref={listRef}
        className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4"
        onMouseUp={captureSelection}
        onScroll={() => setPromote(null)}
      >
        {history.error && (
          <Alert variant="destructive" className={cn('border-glass-border')}>
            <AlertDescription>{history.error.message}</AlertDescription>
          </Alert>
        )}
        {answers.length === 0 && !showLive && (
          <p className="text-sm text-muted-foreground">Ask a question about this paper. Answers cite the passages they use.</p>
        )}
        {answers.map((answer) => (
          <ChatAnswer
            key={answer.id}
            outputId={answer.id}
            question={answer.question}
            wholePaper={answer.whole_paper}
            sources={answer.sources}
            segments={splitCitations(answer.content, knownLabels(answer))}
            footer={{ model: answer.model, promptVersion: answer.prompt_version }}
            onCite={onCite}
          />
        ))}
        {showLive && (
          <ChatAnswer
            question={stream.question}
            wholePaper={stream.wholePaper}
            sources={stream.sources}
            segments={stream.segments}
            footer={stream.done && { model: stream.done.model, promptVersion: stream.done.prompt_version }}
            pending={busy}
            onCite={onCite}
          >
            {stream.problem && <ProblemAlert paperId={paperId} problem={stream.problem} onRetry={retry} />}
          </ChatAnswer>
        )}
      </div>

      {/* Outside the list, so pressing it doesn't re-run the list's mouseup selection check. */}
      {promote && (
        <SaveAsNoteButton
          canSave={promote.draft.chunkIds.length > 0}
          saving={promoteNote.isPending}
          error={promoteError}
          style={promote.style}
          onSave={() => void saveAsNote()}
        />
      )}

      <form
        className="flex flex-col gap-2 border-t border-glass-border p-3"
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <Textarea
          ref={textareaRef}
          aria-label="Question"
          placeholder="Ask about this paper. Enter sends, Shift+Enter adds a line."
          rows={2}
          maxLength={MAX_QUESTION}
          value={question}
          disabled={busy}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault()
              submit()
            }
          }}
        />
        <Button type="submit" size="sm" className="self-end" disabled={busy || !question.trim()}>
          Ask
        </Button>
      </form>
    </div>
  )
}

function ProblemAlert({ paperId, problem, onRetry }: { paperId: string; problem: ChatProblem; onRetry: () => void }) {
  const reindex = useReindexPaper(paperId)
  const message = reindex.isSuccess
    ? 'Re-indexing started. Ask again once the paper is ready.'
    : (reindex.error?.message ?? problem.message)
  return (
    <Alert variant="destructive" className={cn('chat-error border-glass-border')}>
      <AlertDescription>{message}</AlertDescription>
      <AlertAction>
        {problem.retryable && (
          <Button variant="outline" size="xs" onClick={onRetry}>
            Retry
          </Button>
        )}
        {problem.reindex && !reindex.isSuccess && (
          <Button variant="outline" size="xs" disabled={reindex.isPending} onClick={() => reindex.mutate()}>
            Re-index
          </Button>
        )}
      </AlertAction>
    </Alert>
  )
}
