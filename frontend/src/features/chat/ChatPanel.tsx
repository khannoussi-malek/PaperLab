import { ArrowUp, MessageSquareText } from 'lucide-react'
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import type { ChatScope, ChatSource, Note, NoteSource, ChatAnswer as SavedAnswer } from '@/api/client'
import { useChatHistory, usePromoteNote, useReindexPaper } from '@/api/queries'
import { pressable } from '@/components/motion'
import { Alert, AlertAction, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { readAnswerSelection } from './answerSelection'
import { ChatAnswer } from './ChatAnswer'
import { splitCitations } from './citations'
import { promoteSelection, type PromoteDraft } from './promote'
import type { ChatProblem } from './refusals'
import { SaveAsNoteButton } from './SaveAsNoteButton'
import { useChatStream } from './useChatStream'

const MAX_QUESTION = 2000 // the API's limit (spec §3.10)
// ponytail: a fixed width keeps the floating button inside the panel; measure it if the label ever changes.
const SAVE_BUTTON_WIDTH = 140
// What an empty chat offers, by scope: a workspace's starter questions look across its papers.
const EMPTY_CHAT = {
  paper: {
    heading: 'Ask this paper',
    help: 'Answers cite the passages they use. Click a citation to see it in the paper.',
    starters: ['Summarize the main contribution', 'What method do they use?', 'What are the limitations?'],
  },
  workspace: {
    heading: 'Ask this workspace',
    help: 'Answers cite passages from its papers and your notes. Click a citation to open it in the paper.',
    starters: ['Compare their main contributions', 'How do their methods differ?', 'What do my notes say about them?'],
  },
}

/** Labels whose chunk or note still exists; markers for any other label render as plain text. */
const knownLabels = (answer: SavedAnswer) =>
  new Set([...answer.sources, ...answer.notes].flatMap((source) => (source ? [source.label] : [])))

/** A readable reason a promote failed. The API's own codes aren't meant for display. */
function promoteErrorMessage(message: string): string {
  return message === 'body_not_in_output'
    ? "This selection doesn't match the saved answer. Select the text again."
    : "Couldn't save the note. Try again."
}

type Props = {
  scope: ChatScope
  /** Why nothing can be asked yet (an empty workspace): shown under the disabled question box. */
  unavailable?: string
  /** Names a source's paper in pills and citations. Given on a workspace, whose answers cite several papers. */
  paperLabel?: (paperId: string) => string
  onCite: (source: ChatSource | NoteSource) => void
  /** Called with the new note once it is saved and listed. */
  onPromoted: (note: Note) => void
}

type Promote = { outputId: string; draft: PromoteDraft; style: CSSProperties }

export function ChatPanel({ scope, unavailable, paperLabel, onCite, onPromoted }: Props) {
  const history = useChatHistory(scope)
  const { stream, ask, retry } = useChatStream(scope)
  const [question, setQuestion] = useState('')
  const [promote, setPromote] = useState<Promote | null>(null)
  const [promoteError, setPromoteError] = useState<string | null>(null)
  const promoteNote = usePromoteNote()
  const rootRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const wasBusy = useRef(false)
  const answers = history.data ?? []
  const busy = stream.status === 'sources' || stream.status === 'streaming'
  const closed = busy || unavailable !== undefined
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
    if (!text || closed) return
    setQuestion('')
    void ask(text)
  }

  return (
    <div ref={rootRef} className="relative flex min-h-0 flex-1 flex-col">
      {/* `relative`: absolutely positioned children (sr-only labels) must be clipped by this scroller, not escape it
          and stretch the whole page. */}
      <div
        ref={listRef}
        className="relative flex min-h-0 flex-1 flex-col gap-6 overflow-auto p-4"
        onMouseUp={captureSelection}
        onScroll={() => setPromote(null)}
      >
        {history.error && (
          <Alert variant="destructive" className={cn('border-glass-border')}>
            <AlertDescription>{history.error.message}</AlertDescription>
          </Alert>
        )}
        {answers.length === 0 && !showLive && !history.isPending && (
          <EmptyChat kind={scope.kind} disabled={closed} onAsk={(text) => void ask(text)} />
        )}
        {answers.map((answer) => (
          <ChatAnswer
            key={answer.id}
            outputId={answer.id}
            question={answer.question}
            wholePaper={answer.whole_paper}
            sources={answer.sources}
            notes={answer.notes}
            notesUsed={answer.notes_used}
            notesTotal={answer.notes_total}
            segments={splitCitations(answer.content, knownLabels(answer))}
            footer={{ model: answer.model, promptVersion: answer.prompt_version }}
            paperLabel={paperLabel}
            onCite={onCite}
          />
        ))}
        {showLive && (
          <ChatAnswer
            question={stream.question}
            wholePaper={stream.wholePaper}
            sources={stream.sources}
            notes={stream.notes}
            notesUsed={stream.notesUsed}
            notesTotal={stream.notesTotal}
            segments={stream.segments}
            footer={stream.done && { model: stream.done.model, promptVersion: stream.done.prompt_version }}
            pending={busy}
            animate
            paperLabel={paperLabel}
            onCite={onCite}
          >
            {stream.problem && <ProblemAlert scope={scope} problem={stream.problem} onRetry={retry} />}
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
        className="flex flex-col gap-1.5 border-t border-glass-border p-3"
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        {/* One field-looking box: the ring moves from the textarea to the box so the send button sits inside it. */}
        <div className="flex items-end gap-2 rounded-xl border border-input bg-glass-strong p-1.5 pl-3 transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50">
          <Textarea
            ref={textareaRef}
            aria-label="Question"
            aria-describedby="chat-question-hint"
            placeholder={`Ask about this ${scope.kind}…`}
            rows={1}
            maxLength={MAX_QUESTION}
            value={question}
            disabled={closed}
            className="max-h-40 min-h-0 resize-none rounded-none border-0 bg-transparent px-0 py-1 focus-visible:ring-0 disabled:bg-transparent dark:bg-transparent dark:disabled:bg-transparent"
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                submit()
              }
            }}
          />
          <Button type="submit" size="icon-sm" aria-label="Ask" className={pressable} disabled={closed || !question.trim()}>
            <ArrowUp aria-hidden />
          </Button>
        </div>
        <p id="chat-question-hint" className="px-1 text-xs text-muted-foreground">
          {unavailable ?? 'Enter to send · Shift+Enter for a new line'}
        </p>
      </form>
    </div>
  )
}

type EmptyChatProps = { kind: ChatScope['kind']; disabled: boolean; onAsk: (question: string) => void }

function EmptyChat({ kind, disabled, onAsk }: EmptyChatProps) {
  const { heading, help, starters } = EMPTY_CHAT[kind]
  return (
    <div className="m-auto flex w-full max-w-xs flex-col items-center gap-3 py-6 text-center">
      <span className="flex size-10 items-center justify-center rounded-full bg-provenance-llm-surface text-provenance-llm">
        <MessageSquareText aria-hidden className="size-5" />
      </span>
      <h2 className="font-heading text-xl font-semibold">{heading}</h2>
      <p className="text-sm text-muted-foreground">{help}</p>
      <ul aria-label="Suggested questions" className="mt-1 flex w-full flex-col gap-2">
        {starters.map((starter) => (
          <li key={starter}>
            <Button
              variant="outline"
              size="sm"
              className={cn('h-auto w-full justify-start bg-glass-strong py-1.5 text-left whitespace-normal', pressable)}
              disabled={disabled}
              onClick={() => onAsk(starter)}
            >
              {starter}
            </Button>
          </li>
        ))}
      </ul>
    </div>
  )
}

function ProblemAlert({ scope, problem, onRetry }: { scope: ChatScope; problem: ChatProblem; onRetry: () => void }) {
  // Only a paper's `paper_not_indexed` refusal offers Re-index, so `scope` is a paper whenever that button shows.
  const reindex = useReindexPaper(scope.id)
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
