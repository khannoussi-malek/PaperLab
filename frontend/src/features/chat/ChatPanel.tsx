import { ArrowUp } from 'lucide-react'
import { Fragment, useEffect, useRef, useState } from 'react'
import type { ChatScope, ChatSource, Note, NoteSource } from '@/entities'
import { useAskChart, useChatHistory, useChatModels, useSkills } from '@/services/queries'
import { pressable } from '@/components/motion'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { browserStorage } from '@/components/highlightColors'
import { cn } from '@/lib/utils'
import { loadChatModel, saveChatModel } from './chatModel'
import { SaveAsNoteButton } from './SaveAsNoteButton'
import { resolveSkill } from './skillChoice'
import { threadOrder } from './threads'
import { useChatStream } from './useChatStream'
import { useVoiceTurn } from '@/features/voice/useVoiceTurn'
import { looksPerPaper } from './eachPaperHint'
import { VoiceButton } from '@/features/voice/VoiceButton'
import { EmptyChat } from './EmptyChat'
import { ThreadAnswer } from './ThreadAnswer'
import { LiveAnswer } from './LiveAnswer'
import { ComposerAlerts, ComposerOptions, FollowingChip } from './ChatComposerParts'
import { useAnswerPromote } from './useAnswerPromote'

const MAX_QUESTION = 2000 // the API's limit (spec §3.10)
// How close to the bottom (px) still counts as "at the bottom", so a streaming answer keeps the list following it.
const FOLLOW_THRESHOLD = 48

type Props = {
  scope: ChatScope
  /** Why nothing can be asked yet (an empty workspace): shown under the disabled question box. */
  unavailable?: string
  /** Something worth knowing about the answers right now, shown above the question box. */
  notice?: string
  /** Names a source's paper in pills and citations. Given on a workspace, whose answers cite several papers. */
  paperLabel?: (paperId: string) => string
  onCite: (source: ChatSource | NoteSource) => void
  /** A hit chat's first event says whether it reads the full text or the abstract only. */
  onSource?: (source: 'abstract' | 'full_text') => void
  /** Called with the new note once it is saved and listed. */
  onPromoted: (note: Note) => void
}

export function ChatPanel({ scope, unavailable, notice, paperLabel, onCite, onSource, onPromoted }: Props) {
  const history = useChatHistory(scope)
  const chatModels = useChatModels()
  const [pick, setPick] = useState<string | null>(null)
  // The last pick while it's still listed; else the remembered or default one; null only while models are loading.
  const modelId = chatModels.data
    ? pick !== null && chatModels.data.some((model) => model.id === pick)
      ? pick
      : loadChatModel(browserStorage(), chatModels.data)
    : null
  // The skill the reader picked this session; undefined until they pick (the kind's default), null for No skill.
  // A search hit's chat has no skills, so its question sends none.
  const skills = useSkills(scope.kind === 'hit' ? 'paper' : scope.kind, false, scope.kind !== 'hit')
  const [skillPick, setSkillPick] = useState<string | null | undefined>(undefined)
  const skillId = scope.kind === 'hit' ? null : resolveSkill(skills.data ?? [], scope.kind, skillPick)
  // The saved answer the next question follows up (paper chat only); null asks it on its own.
  const [followingId, setFollowingId] = useState<string | null>(null)
  const typed = useChatStream(scope, modelId, skillId, (parentId, next) =>
    // Only while the chip still names the answer that question followed: × pressed mid-stream stays pressed.
    setFollowingId((current) => (current === parentId ? next : current)),
  )
  const voice = useVoiceTurn(scope, modelId)
  // Which of the two asked last: the live answer shows that one's stream.
  const [liveSource, setLiveSource] = useState<'typed' | 'voice'>('typed')
  const voiceAsked = voice.stream.status === 'sources'
  const [wasVoiceAsked, setWasVoiceAsked] = useState(false)
  if (voiceAsked !== wasVoiceAsked) {
    setWasVoiceAsked(voiceAsked)
    if (voiceAsked) setLiveSource('voice')
  }
  const stream = liveSource === 'voice' ? voice.stream : typed.stream
  const { retry } = typed
  function ask(text: string, parentId: string | null = null, eachPaper = false) {
    setLiveSource('typed')
    return typed.ask(text, parentId, eachPaper)
  }
  const [question, setQuestion] = useState('')
  // M14: the next question asks for a chart of the scope's captured data instead of a written answer.
  const [chartMode, setChartMode] = useState(false)
  // M8.5 (workspace chat): read each paper on its own first, then answer from what each says.
  const [eachPaper, setEachPaper] = useState(false)
  const askChart = useAskChart(scope)
  const streamSource = stream.source
  useEffect(() => {
    if (streamSource) onSource?.(streamSource)
  }, [streamSource]) // eslint-disable-line react-hooks/exhaustive-deps -- fires on the event, not on a new callback
  const rootRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const wasBusy = useRef(false)
  // Whether the list was scrolled to (near) its bottom, so a streaming answer only pulls it along when it was
  // already following. Starts true: the first tokens of a freshly asked question should always pull it down.
  const followRef = useRef(true)
  const answers = history.data ?? []
  const busy = stream.status === 'sources' || stream.status === 'streaming'
  const typedBusy = typed.stream.status === 'sources' || typed.stream.status === 'streaming'
  const noModels = chatModels.data?.length === 0
  // `isPending`: the first models fetch hasn't settled yet, so modelId is still null. Once it fails, isPending
  // clears and asking stays open with no model id, which the API answers with the owner's default; the composer
  // says so instead of leaving an empty gap where the dropdown was.
  const unusable = unavailable !== undefined || noModels || chatModels.isPending
  // A spoken question or its answer under way holds the box too: two answers at once would share one live slot.
  const closed = busy || askChart.isPending || voice.state === 'thinking' || voice.state === 'speaking' || unusable
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

  const { promote, promoteError, savePending, captureSelection, saveAsNote, hidePromote } = useAnswerPromote({
    answers,
    rootRef,
    onPromoted,
  })

  function submit() {
    const text = question.trim()
    if (!text || closed) return
    if (chartMode && scope.kind !== 'hit') {
      // The question stays until the chart is saved, so a refusal can be reworded rather than retyped.
      // A chart stands on its own: it doesn't follow up an earlier answer, so the Following chip goes.
      setFollowingId(null)
      askChart.mutate({ question: text, modelId }, { onSuccess: () => setQuestion('') })
      return
    }
    setQuestion('')
    void ask(text, followingId, scope.kind === 'workspace' && eachPaper)
  }

  function followUp(answerId: string) {
    setFollowingId(answerId)
    textareaRef.current?.focus()
  }

  // The answer being asked now, shown at the end of the thread it follows up, or last, until its saved copy is listed.
  const liveNode = showLive && (
    <LiveAnswer
      scope={scope}
      stream={stream}
      liveReply={liveReply}
      busy={busy}
      retry={retry}
      paperLabel={paperLabel}
      onCite={onCite}
    />
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
          hidePromote()
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
            {index === liveAt && liveNode}
            <ThreadAnswer
              answer={answer}
              reply={reply}
              scope={scope}
              closed={closed}
              paperLabel={paperLabel}
              onCite={onCite}
              onFollowUp={followUp}
            />
          </Fragment>
        ))}
        {liveAt === placed.length && liveNode}
      </div>

      {/* Outside the list, so pressing it doesn't re-run the list's mouseup selection check. */}
      {promote && (
        <SaveAsNoteButton
          canSave={promote.draft.chunkIds.length > 0}
          saving={savePending}
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
        {notice && <p className="px-1 text-xs text-muted-foreground">{notice}</p>}
        {followingQuestion !== null && <FollowingChip question={followingQuestion} onStop={() => setFollowingId(null)} />}
        {/* One field-looking box: the ring moves from the textarea to the box so the send button sits inside it. */}
        <div className="flex items-end gap-2 rounded-xl border border-input bg-glass-strong p-1.5 pl-3 transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50">
          <Textarea
            ref={textareaRef}
            aria-label="Question"
            aria-describedby="chat-question-hint"
            placeholder={`Ask about this ${scope.kind === 'hit' ? 'paper' : scope.kind}…`}
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
          {/* The voice server answers paper and workspace chats only; a search hit's chat stays typed. */}
          {scope.kind !== 'hit' && <VoiceButton voice={voice} disabled={typedBusy || unusable} />}
          <Button type="submit" size="icon-sm" aria-label="Ask" className={pressable} disabled={closed || !question.trim()}>
            <ArrowUp aria-hidden />
          </Button>
        </div>
        {chatModels.data && chatModels.data.length > 0 && (
          <ComposerOptions
            kind={scope.kind}
            models={chatModels.data}
            modelId={modelId}
            onPickModel={pickModel}
            skills={skills.data}
            skillId={skillId}
            onSkillPick={setSkillPick}
            eachPaper={eachPaper}
            setEachPaper={setEachPaper}
            chartMode={chartMode}
            setChartMode={setChartMode}
          />
        )}
        {scope.kind === 'workspace' && !eachPaper && looksPerPaper(question) && (
          <Button
            type="button"
            size="xs"
            variant="ghost"
            className="self-start text-muted-foreground"
            aria-label="Sounds like a question for each paper · Ask each paper"
            onClick={() => setEachPaper(true)}
          >
            <span>Sounds like a question for each paper</span>
            <span> · Ask each paper</span>
          </Button>
        )}
        <ComposerAlerts
          kind={scope.kind}
          chartError={askChart.error}
          voiceProblem={voice.problem}
          modelsError={chatModels.isError}
          noModels={noModels}
          unavailable={unavailable}
        />
      </form>
    </div>
  )
}
