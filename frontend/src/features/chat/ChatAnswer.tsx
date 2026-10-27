import { CornerDownRight, Sparkles } from 'lucide-react'
import { Fragment, useMemo, useState, type ReactNode } from 'react'
import type { ChatScope, ChatSource, NoteSource, SavedNote } from '@/api/client'
import { pressable, slideUpIn } from '@/components/motion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { aiMark } from './aiMark'
import { MARKER, describeSource, splitCitations, type Segment } from './citations'
import { markdownPieces } from './markdown'
import { renderPieces } from './renderPieces'
import { splitNoteBlocks } from './noteBlocks'
import { SuggestedNote } from './SuggestedNote'
import { Term } from '@/features/workspaces/Term'
import { Scene3D } from '@/features/scene3d/Scene3D'

const loadChatScene = () => import('@/features/scene3d/directors/chat')

type Props = {
  question: string
  wholePaper: boolean
  /** In label order (C1, C2, …). An entry is null when a re-ingest replaced its chunk; the list is null until known. */
  sources: (ChatSource | null)[] | null
  /** The notes it could cite, in label order (N1, N2, …), null once deleted. */
  notes: (NoteSource | null)[]
  /** How many notes fit the prompt, of how many; null on paper answers saved before notes were sent. */
  notesUsed: number | null
  notesTotal: number | null
  segments: Segment[]
  /** Set once the answer is saved: the model label is only known then. */
  footer: { model: string; connectionName: string | null; promptVersion: number } | null
  /** The saved answer's `llm_outputs` id; absent while it streams. */
  outputId?: string
  /** The answer this one follows up. `reply` indents it under the first question of its thread. */
  parentId?: string | null
  reply?: boolean
  /** Offered on a saved paper answer: asks the next question as a follow-up to this one. */
  followUp?: { onClick: () => void; disabled: boolean }
  /** Given on a saved answer: where its suggested notes save to, and which are saved already. Absent while an answer
   * streams and until its saved copy is listed, so a card's Save stays disabled. */
  suggestions?: { scope: ChatScope; saved: SavedNote[] }
  pending?: boolean
  /** Fade up on mount: only the answer being asked now, never ones loaded from history. */
  animate?: boolean
  /** Names a source's paper. Given on a workspace, whose answers cite several papers. */
  paperLabel?: (paperId: string) => string
  /** Shows a source: the reader flashes a passage in place; a workspace opens the reader on a passage or a note. */
  onCite: (source: Cited) => void
  /** Shown under the answer, e.g. an error with Retry. */
  children?: ReactNode
}

type Cited = ChatSource | NoteSource

const CITE_HINT = 'The AI used this passage. Click to see it in the paper.'
const ABSTRACT_HINT = "The AI used this paper's abstract: it has no PDF yet. Click to see the abstract."
const NOTE_HINT = 'The AI used this note. Click to see it in the paper.'
const hintFor = (source: Cited) => ('note_id' in source ? NOTE_HINT : source.from_abstract ? ABSTRACT_HINT : CITE_HINT)

export function ChatAnswer(props: Props) {
  const { question, wholePaper, sources, notes, notesUsed, notesTotal, segments, footer, outputId, pending } = props
  const { animate, paperLabel, onCite, children, parentId, reply, followUp, suggestions } = props
  const sourceFor = (label: string) => [...(sources ?? []), ...notes].find((source) => source?.label === label)
  const describe = (source: Cited) => describeSource(source, paperLabel?.(source.paper_id))
  const waiting = pending && segments.length === 0
  const content = segments.map((segment) => (segment.kind === 'text' ? segment.text : `[${segment.label}]`)).join('')
  // Prose, suggested notes and the marker lines between them, each with its own markdown; the parts tile `content`.
  const rendered = useMemo(
    () =>
      splitNoteBlocks(content).map((part) => ({
        part,
        pieces: part.kind === 'marker' ? [] : markdownPieces(content.slice(part.start, part.end)),
      })),
    [content],
  )
  const cited = new Set(segments.flatMap((segment) => (segment.kind === 'cite' ? [segment.label] : [])))
  const known = new Set([...(sources ?? []), ...notes].flatMap((source) => (source ? [source.label] : [])))
  // Labels are positional (C1…, N1…), so a label within the answer's lists named a real source when it was written,
  // even if that slot is null now (re-ingested, or a note deleted): only one past the end was invented.
  const beyondSources = (label: string) =>
    Number(label.slice(1)) > (label.startsWith('C') ? (sources ?? []).length : notes.length)
  // Once the sources are known every marker is split out, so one that matches none of them shows flagged (M72)
  // rather than as plain text that reads like a real citation. Until then, unknown labels stay text.
  const renderText = (text: string) =>
    splitCitations(text, sources === null ? known : new Set([...text.matchAll(MARKER)].map((m) => m[1]))).map((segment, i) => {
      const source = segment.kind === 'cite' ? sourceFor(segment.label) : undefined
      if (!source && segment.kind === 'cite' && beyondSources(segment.label)) {
        return <UnknownCitation key={i} label={segment.label} />
      }
      // The tooltip renders in a portal, so the answer's text (which promote.ts counts) is unchanged.
      return source ? (
        <Hint key={i} label={describe(source)} detail={hintFor(source)}>
          <button
            type="button"
            className="chat-cite rounded-xs font-medium text-primary underline-offset-2 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
            aria-label={describe(source)}
            onClick={() => onCite(source)}
          >
            [{source.label}]
          </button>
        </Hint>
      ) : (
        <span key={i}>{segment.kind === 'text' ? segment.text : `[${segment.label}]`}</span>
      )
    })
  return (
    <article
      className={cn('chat-answer flex flex-col gap-2', reply && 'ml-3 border-l border-glass-border pl-3', animate && slideUpIn)}
      data-output-id={outputId}
      data-parent-id={parentId ?? undefined}
    >
      <p className="chat-question max-w-[85%] self-end rounded-2xl rounded-br-sm bg-glass-strong px-3 py-2 text-sm whitespace-pre-wrap ring-1 ring-glass-border">
        {question}
      </p>

      {(sources !== null || pending) && (
        // AI text sits on the opaque provenance surface, never on glass (D26).
        // Plain-text hints, so not hoverable: a wide open tooltip keeps a "pointer heading to the tooltip" zone over
        // the neighbouring pill, and moving from C1 onto C2 would keep showing C1's explanation.
        <TooltipProvider disableHoverableContent>
          <div className="flex flex-col gap-3 rounded-2xl bg-provenance-llm-surface p-3.5">
            {waiting ? (
              <TypingIndicator
                label={sources === null ? 'Finding sources…' : 'Writing the answer…'}
                phase={sources === null ? 'sources' : 'thinking'}
              />
            ) : (
              // The text content is exactly the answer, markers and hidden markdown syntax included (promote.ts counts
              // offsets in it); a suggested note's label and buttons are data-chrome, which answerSelection.ts leaves out.
              <div className="chat-answer-text space-y-2 text-sm leading-relaxed whitespace-pre-line">
                {rendered.map(({ part, pieces }) => {
                  const key = `${part.kind}-${part.start}`
                  const text = content.slice(part.start, part.end)
                  // Checked together (not `kind === 'marker'` then `kind === 'prose'`): TS only narrows a union member
                  // away once its discriminant is excluded entirely, and this member's `kind` is itself `'prose' |
                  // 'marker'`, so excluding just one of those literals at a time leaves `part.index` still unreachable.
                  if (part.kind !== 'note') {
                    return part.kind === 'marker' ? (
                      <span key={key} hidden>
                        {text}
                      </span>
                    ) : (
                      <Fragment key={key}>{renderPieces(pieces, renderText)}</Fragment>
                    )
                  }
                  // An empty block renders nothing, but keeps its index for the blocks after it.
                  if (part.end === part.start) return null
                  const save =
                    outputId && suggestions
                      ? { scope: suggestions.scope, outputId, saved: suggestions.saved.find((s) => s.index === part.index) }
                      : undefined
                  return (
                    <SuggestedNote key={key} index={part.index} save={save}>
                      {renderPieces(pieces, renderText)}
                    </SuggestedNote>
                  )
                })}
              </div>
            )}

            {(footer || sources !== null) && (
              <AnswerMeta
                footer={footer}
                sources={sources}
                notes={notes}
                wholePaper={wholePaper}
                cited={cited}
                pending={pending}
                describe={describe}
                onCite={onCite}
                followUp={followUp}
              />
            )}
            {notesUsed !== null && notesTotal !== null && notesUsed < notesTotal && (
              <p className="text-xs text-muted-foreground">
                Using {notesUsed} of {notesTotal} <Term term="notesUsed">notes</Term> (newest first)
              </p>
            )}
          </div>
        </TooltipProvider>
      )}
      {children}
    </article>
  )
}

/**
 * While nothing has streamed yet: a small 3D page with the wire pulling a note off it (or, without WebGL or with
 * reduced motion, three pulsing dots). Screen readers hear the label either way. It unmounts with the first words,
 * so only the answer being written ever holds a WebGL context.
 */
function TypingIndicator({ label, phase }: { label: string; phase: 'sources' | 'thinking' }) {
  const dots = (
    <span className="flex h-6 items-center gap-1">
      {['[animation-delay:-0.3s]', '[animation-delay:-0.15s]', ''].map((delay) => (
        <span key={delay} aria-hidden className={cn('size-1.5 rounded-full bg-provenance-llm motion-safe:animate-bounce', delay)} />
      ))}
    </span>
  )
  return (
    <div role="status" className="flex items-center">
      <span className="sr-only">{label}</span>
      <Scene3D load={loadChatScene} input={{ phase }} fallback={dots} className="h-[72px] w-[120px]" />
    </div>
  )
}

type MetaProps = Pick<Props, 'footer' | 'sources' | 'notes' | 'wholePaper' | 'onCite' | 'followUp' | 'pending'> & {
  /** Labels the answer's text cites; only these show until "Show all". */
  cited: ReadonlySet<string>
  describe: (source: Cited) => string
}

/**
 * One quiet row: the AI mark, then a pill per source. Everything longer (the model, each passage's page and section)
 * waits in a tooltip, so a thread of answers doesn't repeat the same line under each one.
 */
function AnswerMeta({ footer, sources, notes, wholePaper, cited, pending, describe, onCite, followUp }: MetaProps) {
  const [showAll, setShowAll] = useState(false)
  const aiLabel = footer ? aiMark(footer.model, footer.connectionName, footer.promptVersion) : 'AI'
  const pill = (source: Cited | null) =>
    source && (
      <li key={source.label}>
        <Hint label={describe(source)} detail={hintFor(source)}>
          <Button
            variant="outline"
            size="xs"
            className={cn('min-w-8 tabular-nums', pressable)}
            aria-label={describe(source)}
            onClick={() => onCite(source)}
          >
            {source.label}
          </Button>
        </Hint>
      </li>
    )
  const shown = (list: (Cited | null)[]) => (wholePaper || showAll ? list : list.filter((source) => source && cited.has(source.label)))
  const real = wholePaper || sources === null ? 0 : [...sources, ...notes].filter(Boolean).length
  const total = real
  const hidden = real - [...shown(sources ?? []), ...shown(notes)].filter(Boolean).length
  // The pills wrap among themselves, so the AI mark keeps its place at the start of the row.
  return (
    <div className="flex items-start gap-1.5">
      <Hint label={aiLabel}>
        {/* Focusable, so keyboard users reach the tooltip too. The sr-only text is the label, for screen readers. */}
        <span
          tabIndex={0}
          className={cn(
            'flex size-6 shrink-0 items-center justify-center rounded-full text-provenance-llm outline-none focus-visible:ring-2 focus-visible:ring-ring',
            footer && 'chat-answer-footer',
          )}
        >
          <Sparkles aria-hidden className="size-3.5" />
          <span className="sr-only">{aiLabel}</span>
        </span>
      </Hint>
      {sources !== null && (
        <ul className="chat-sources flex min-w-0 flex-1 flex-wrap gap-1" aria-label="Sources">
          {wholePaper ? (
            <li>
              <Badge variant="outline">Whole paper · {sources.length} {sources.length === 1 ? 'chunk' : 'chunks'}</Badge>
            </li>
          ) : (
            shown(sources).map(pill)
          )}
          {shown(notes).map(pill)}
        </ul>
      )}
      {/* A streaming answer shows what it cites so far; the full list waits for the saved answer. */}
      {hidden > 0 && !pending && (
        <Button variant="link" size="xs" className="shrink-0" onClick={() => setShowAll(true)}>
          Show all {total} sources
        </Button>
      )}
      {followUp && (
        <Button
          variant="ghost"
          size="xs"
          className={cn('ml-auto shrink-0 text-muted-foreground', pressable)}
          disabled={followUp.disabled}
          onClick={followUp.onClick}
        >
          <CornerDownRight aria-hidden />
          Follow up
        </Button>
      )}
    </div>
  )
}

const NO_SOURCE = "This citation doesn't match any source the answer was given."

/** A label the model cited that no source carries: shown, so the reader sees the invented reference, but flagged.
 * The "?" is chrome (answerSelection.ts skips it), so a quote saved from the answer stays a verbatim slice. */
function UnknownCitation({ label }: { label: string }) {
  return (
    <Hint label={`${label}?`} detail={NO_SOURCE}>
      <span
        tabIndex={0}
        aria-label={`${label}? ${NO_SOURCE}`}
        className="chat-cite-unknown cursor-help rounded-xs border-b border-dashed border-muted-foreground text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        [{label}
        <span data-chrome>?</span>]
      </span>
    </Hint>
  )
}

function Hint({ label, detail, children }: { label: string; detail?: string; children: ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent className="flex-col items-start gap-0.5">
        <span className="font-medium">{label}</span>
        {detail && <span className="opacity-80">{detail}</span>}
      </TooltipContent>
    </Tooltip>
  )
}
