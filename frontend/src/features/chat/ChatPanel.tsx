import { ArrowUp, CornerDownRight, MessageSquareText, Settings2, X } from 'lucide-react'
import { Fragment, useEffect, useRef, useState, type CSSProperties } from 'react'
import type { ChatScope, ChatSource, Note, NoteSource, ChatAnswer as SavedAnswer } from '@/api/client'
import { useChatHistory, useChatModels, useEmbeddingStatus, usePromoteNote, useReindexPaper } from '@/api/queries'
import { pressable } from '@/components/motion'
import { Alert, AlertAction, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { browserStorage } from '@/features/notes/highlightColors'
import { DownloadSearchModel } from '@/features/settings/DownloadSearchModel'
import { SearchRebuild, SourceError } from '@/features/settings/SearchRebuild'
import { READY_AGAIN } from '@/features/settings/searchSources'
import { settingsHref } from '@/lib/route'
import { cn } from '@/lib/utils'
import { readAnswerSelection } from './answerSelection'
import { ChatAnswer } from './ChatAnswer'
import { loadChatModel, saveChatModel } from './chatModel'
import { splitCitations } from './citations'
import { ModelPicker } from './ModelPicker'
import { promoteErrorMessage, promoteSelection, type PromoteDraft } from './promote'
import type { ChatProblem } from './refusals'
import { saveButtonPosition } from './saveButton'
import { SaveAsNoteButton } from './SaveAsNoteButton'
import { threadOrder } from './threads'
import { useChatStream } from './useChatStream'

const MAX_QUESTION = 2000 // the API's limit (spec §3.10)
// How close to the bottom (px) still counts as "at the bottom", so a streaming answer keeps the list following it.
const FOLLOW_THRESHOLD = 48
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
  const chatModels = useChatModels()
  const [pick, setPick] = useState<string | null>(null)
  // The last pick while it's still listed; else the remembered or default one; null only while models are loading.
  const modelId = chatModels.data
    ? pick !== null && chatModels.data.some((model) => model.id === pick)
      ? pick
      : loadChatModel(browserStorage(), chatModels.data)
    : null
  // The saved answer the next question follows up (paper chat only); null asks it on its own.
  const [followingId, setFollowingId] = useState<string | null>(null)
  const { stream, ask, retry } = useChatStream(scope, modelId, (parentId, next) =>
    // Only while the chip still names the answer that question followed: × pressed mid-stream stays pressed.
    setFollowingId((current) => (current === parentId ? next : current)),
  )
  const [question, setQuestion] = useState('')
  const [promote, setPromote] = useState<Promote | null>(null)
  const [promoteError, setPromoteError] = useState<string | null>(null)
  const promoteNote = usePromoteNote()
  const rootRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const wasBusy = useRef(false)
  // Whether the list was scrolled to (near) its bottom, so a streaming answer only pulls it along when it was
  // already following. Starts true: the first tokens of a freshly asked question should always pull it down.
  const followRef = useRef(true)
  const answers = history.data ?? []
  const busy = stream.status === 'sources' || stream.status === 'streaming'
  const noModels = chatModels.data?.length === 0
  // `isPending`: the first models fetch hasn't settled yet, so modelId is still null. Once it fails, isPending
  // clears and asking stays open with no model id, which the API answers with the owner's default; the composer
  // says so instead of leaving an empty gap where the dropdown was.
  const closed = busy || unavailable !== undefined || noModels || chatModels.isPending
  // A saved answer comes back in the history, so the live copy hides instead of showing twice.
  const showLive = stream.status !== 'idle' && !answers.some((answer) => answer.id === stream.done?.output_id)
  const { placed, liveAt, liveReply } = threadOrder(answers, showLive ? stream.parentId : null)
  // The chip names the followed answer; a just-saved one isn't in the refetched history for a moment yet.
  const followingQuestion =
    followingId === null
      ? null
      : (answers.find((answer) => answer.id === followingId)?.question ??
        (stream.done?.output_id === followingId ? stream.question : null))

  function pickModel(id: string) {
    setPick(id)
    saveChatModel(browserStorage(), id)
  }

  // Follows a streaming answer down as its tokens arrive, but only while the list was already at the bottom: a
  // question just asked (`sources`) always scrolls, since that's the moment the reader expects to see it appear.
  // A follow-up to an older thread appears inside that thread, so it scrolls into view rather than to the bottom.
  useEffect(() => {
    if (stream.status === 'sources' && stream.parentId !== null) {
      listRef.current?.querySelector('article.chat-answer:not([data-output-id])')?.scrollIntoView({ block: 'nearest' })
    } else if (followRef.current || stream.status === 'sources') {
      listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
    }
  }, [answers.length, stream.status, stream.segments, stream.parentId])

  // Enter disables the Textarea while busy, so the browser blurs it to <body>; bring focus back once it clears.
  useEffect(() => {
    if (wasBusy.current && !busy) textareaRef.current?.focus()
    wasBusy.current = busy
  }, [busy])

  function captureSelection() {
    const selected = readAnswerSelection()
    const answer = answers.find((a) => a.id === selected?.outputId)
    const draft = selected && answer && promoteSelection(answer.content, answer.sources, selected.anchor, selected.focus)
    const box = rootRef.current?.getBoundingClientRect()
    if (!selected || !draft || !box) {
      setPromote(null)
      setPromoteError(null)
      return
    }
    // Only a genuinely different selection retires a shown error: a recapture of the *same* selection (a resize, or
    // any other re-run of this function) must not silently clear an error the user hasn't acted on yet.
    if (promote?.outputId !== selected.outputId || promote?.draft.body !== draft.body) setPromoteError(null)
    setPromote({ outputId: selected.outputId, draft, style: saveButtonPosition(selected.rect, box) })
  }

  // The selection can change without a mouseup: dragging still fires this repeatedly, and so does
  // Shift+Arrow. Re-running the full capture (not just hiding on collapse) keeps the draft live, not stale.
  useEffect(() => {
    document.addEventListener('selectionchange', captureSelection)
    return () => document.removeEventListener('selectionchange', captureSelection)
  })

  // The freshest captureSelection, for the ResizeObserver below: observing must start exactly once (`observe()`
  // itself fires one immediate callback, so re-subscribing on every render would re-fire it every render too, right
  // after any state change -- including the one that had just set an error, clearing it straight back out).
  const captureSelectionRef = useRef(captureSelection)
  useEffect(() => {
    captureSelectionRef.current = captureSelection
  })

  // The panel (or the split it sits in) can change size from under an open selection: a drag on the resize handle,
  // or coming back to a tab that was hidden. Re-measuring keeps the button under its selection either way.
  useEffect(() => {
    const node = rootRef.current
    if (!node) return
    const observer = new ResizeObserver(() => captureSelectionRef.current())
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

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
      setPromoteError(promoteErrorMessage(e))
    }
  }

  function submit() {
    const text = question.trim()
    if (!text || closed) return
    setQuestion('')
    void ask(text, followingId)
  }

  function followUp(answerId: string) {
    setFollowingId(answerId)
    textareaRef.current?.focus()
  }

  // The answer being asked now: at the end of the thread it follows up, or last, until its saved copy is listed.
  const liveAnswer = () =>
    showLive && (
      <ChatAnswer
        question={stream.question}
        parentId={stream.parentId}
        reply={liveReply}
        wholePaper={stream.wholePaper}
        sources={stream.sources}
        notes={stream.notes}
        notesUsed={stream.notesUsed}
        notesTotal={stream.notesTotal}
        segments={stream.segments}
        footer={
          stream.done && { model: stream.done.model, connectionName: stream.done.connection_name, promptVersion: stream.done.prompt_version }
        }
        pending={busy}
        animate
        paperLabel={paperLabel}
        onCite={onCite}
      >
        {stream.problem && <ProblemAlert scope={scope} problem={stream.problem} onRetry={retry} />}
      </ChatAnswer>
    )

  return (
    <div ref={rootRef} className="relative flex min-h-0 flex-1 flex-col">
      {/* `relative`: absolutely positioned children (sr-only labels) must be clipped by this scroller, not escape it
          and stretch the whole page. */}
      <div
        ref={listRef}
        className="relative flex min-h-0 flex-1 flex-col gap-6 overflow-auto p-4"
        onMouseUp={captureSelection}
        onScroll={(e) => {
          const el = e.currentTarget
          followRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < FOLLOW_THRESHOLD
          setPromote(null)
        }}
      >
        {history.error && (
          <Alert variant="destructive" className={cn('border-glass-border')}>
            <AlertDescription>{history.error.message}</AlertDescription>
          </Alert>
        )}
        {answers.length === 0 && !showLive && !history.isPending && (
          <EmptyChat kind={scope.kind} disabled={closed} onAsk={(text) => void ask(text)} />
        )}
        {placed.map(({ answer, reply }, index) => (
          <Fragment key={answer.id}>
            {index === liveAt && liveAnswer()}
            <ChatAnswer
              outputId={answer.id}
              parentId={answer.parent_id}
              reply={reply}
              question={answer.question}
              wholePaper={answer.whole_paper}
              sources={answer.sources}
              notes={answer.notes}
              notesUsed={answer.notes_used}
              notesTotal={answer.notes_total}
              segments={splitCitations(answer.content, knownLabels(answer))}
              footer={{ model: answer.model, connectionName: answer.connection_name, promptVersion: answer.prompt_version }}
              paperLabel={paperLabel}
              onCite={onCite}
              followUp={scope.kind === 'paper' ? { onClick: () => followUp(answer.id), disabled: closed } : undefined}
            />
          </Fragment>
        ))}
        {liveAt === placed.length && liveAnswer()}
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
        {followingQuestion !== null && (
          <p className="chat-following flex min-w-0 items-center gap-1.5 px-1 text-xs text-muted-foreground">
            <CornerDownRight aria-hidden className="size-3.5 shrink-0" />
            <span className="min-w-0 truncate" title={followingQuestion}>
              Following: {followingQuestion}
            </span>
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              className={cn('ml-auto', pressable)}
              aria-label="Stop following"
              onClick={() => setFollowingId(null)}
            >
              <X aria-hidden />
            </Button>
          </p>
        )}
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
        {chatModels.data && chatModels.data.length > 0 && (
          <div className="flex">
            <ModelPicker models={chatModels.data} value={modelId} onChange={pickModel} />
          </div>
        )}
        {chatModels.isError && <p className="px-1 text-xs text-muted-foreground">Couldn’t load your models; using the default.</p>}
        {noModels && (
          <a href={settingsHref} className="inline-flex w-fit items-center gap-1.5 text-sm text-muted-foreground transition-colors duration-150 hover:text-foreground">
            <Settings2 aria-hidden className="size-3.5" />
            Set up a model
          </a>
        )}
        <p id="chat-question-hint" className="px-1 text-xs text-muted-foreground">
          {unavailable ?? (noModels ? 'Set up a model to chat.' : 'Enter to send · Shift+Enter for a new line')}
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
  const embedding = useEmbeddingStatus()
  // search_rebuilding (P1): the rebuild's line and bar while it runs, the status polling meanwhile. `undefined` while
  // the status loads counts as still running. Once it is done, say so and offer Retry.
  const waiting = problem.rebuild === true && embedding.data?.rebuild !== null
  const reindexed = reindex.isSuccess ? 'Re-indexing started. Ask again once the paper is ready.' : undefined
  const message = problem.rebuild
    ? waiting
      ? problem.message
      : READY_AGAIN
    : (reindexed ?? reindex.error?.message ?? problem.message)
  return (
    <>
      <Alert variant="destructive" className={cn('chat-error border-glass-border')}>
        {waiting && embedding.data?.rebuild ? <SearchRebuild /> : <AlertDescription>{message}</AlertDescription>}
        {problem.download && (
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
            <DownloadSearchModel />
            <a href={settingsHref} className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">
              Use another search source
            </a>
          </div>
        )}
        <AlertAction>
          {problem.retryable && !waiting && (
            <Button variant="outline" size="xs" onClick={onRetry}>
              Retry
            </Button>
          )}
          {problem.reindex && !reindex.isSuccess && (
            <Button variant="outline" size="xs" disabled={reindex.isPending} onClick={() => reindex.mutate()}>
              Re-index
            </Button>
          )}
          {problem.settings && (
            <Button variant="outline" size="xs" asChild>
              <a href={settingsHref}>Open settings</a>
            </Button>
          )}
        </AlertAction>
      </Alert>
      {/* D155: a paper that keeps failing keeps search paused; the reason and Try again are here too. */}
      {waiting && <SourceError />}
    </>
  )
}
