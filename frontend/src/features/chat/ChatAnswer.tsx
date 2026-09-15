import { Sparkles } from 'lucide-react'
import type { ReactNode } from 'react'
import type { ChatSource, NoteSource } from '@/api/client'
import { pressable, slideUpIn } from '@/components/motion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { aiMark } from './aiMark'
import { describeSource, type Segment } from './citations'

type Props = {
  question: string
  wholePaper: boolean
  /** In label order (C1, C2, …). An entry is null when a re-ingest replaced its chunk; the list is null until known. */
  sources: (ChatSource | null)[] | null
  /** Workspace chat: the notes it could cite, in label order (N1, N2, …), null once deleted. Empty in the reader. */
  notes: (NoteSource | null)[]
  /** How many of the workspace's notes fit the prompt, of how many; null in the reader. */
  notesUsed: number | null
  notesTotal: number | null
  segments: Segment[]
  /** Set once the answer is saved: the model label is only known then. */
  footer: { model: string; connectionName: string | null; promptVersion: number } | null
  /** The saved answer's `llm_outputs` id; absent while it streams. */
  outputId?: string
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
const NOTE_HINT = 'The AI used this note. Click to see it in the paper.'
const hintFor = (source: Cited) => ('note_id' in source ? NOTE_HINT : CITE_HINT)

export function ChatAnswer(props: Props) {
  const { question, wholePaper, sources, notes, notesUsed, notesTotal, segments, footer, outputId, pending } = props
  const { animate, paperLabel, onCite, children } = props
  const sourceFor = (label: string) => [...(sources ?? []), ...notes].find((source) => source?.label === label)
  const describe = (source: Cited) => describeSource(source, paperLabel?.(source.paper_id))
  const waiting = pending && segments.length === 0
  return (
    <article className={cn('chat-answer flex flex-col gap-2', animate && slideUpIn)} data-output-id={outputId}>
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
              <TypingIndicator label={sources === null ? 'Finding sources…' : 'Writing the answer…'} />
            ) : (
              // The text content is exactly the answer, markers included: promote.ts counts offsets in it.
              <p className="chat-answer-text text-sm leading-relaxed whitespace-pre-wrap">
                {segments.map((segment, i) => {
                  const source = segment.kind === 'cite' ? sourceFor(segment.label) : undefined
                  // The tooltip renders in a portal, so the paragraph's text (which promote.ts counts) is unchanged.
                  return source ? (
                    <Hint key={i} label={describe(source)} detail={hintFor(source)}>
                      <button
                        type="button"
                        className="chat-cite rounded-xs font-medium text-primary underline-offset-2 hover:underline"
                        aria-label={describe(source)}
                        onClick={() => onCite(source)}
                      >
                        [{source.label}]
                      </button>
                    </Hint>
                  ) : (
                    <span key={i}>{segment.kind === 'text' ? segment.text : `[${segment.label}]`}</span>
                  )
                })}
              </p>
            )}

            {(footer || sources !== null) && (
              <AnswerMeta
                footer={footer}
                sources={sources}
                notes={notes}
                wholePaper={wholePaper}
                describe={describe}
                onCite={onCite}
              />
            )}
            {notesUsed !== null && notesTotal !== null && notesUsed < notesTotal && (
              <p className="text-xs text-muted-foreground">
                Using {notesUsed} of {notesTotal} notes (newest first)
              </p>
            )}
          </div>
        </TooltipProvider>
      )}
      {children}
    </article>
  )
}

/** Three pulsing dots while nothing has streamed yet; screen readers hear the label instead. */
function TypingIndicator({ label }: { label: string }) {
  return (
    <p role="status" className="flex h-6 items-center gap-1">
      <span className="sr-only">{label}</span>
      {['[animation-delay:-0.3s]', '[animation-delay:-0.15s]', ''].map((delay) => (
        <span key={delay} aria-hidden className={cn('size-1.5 rounded-full bg-provenance-llm motion-safe:animate-bounce', delay)} />
      ))}
    </p>
  )
}

type MetaProps = Pick<Props, 'footer' | 'sources' | 'notes' | 'wholePaper' | 'onCite'> & {
  describe: (source: Cited) => string
}

/**
 * One quiet row: the AI mark, then a pill per source. Everything longer (the model, each passage's page and section)
 * waits in a tooltip, so a thread of answers doesn't repeat the same line under each one.
 */
function AnswerMeta({ footer, sources, notes, wholePaper, describe, onCite }: MetaProps) {
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
              <Badge variant="outline">Whole paper · {sources.length} chunks</Badge>
            </li>
          ) : (
            sources.map(pill)
          )}
          {notes.map(pill)}
        </ul>
      )}
    </div>
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
