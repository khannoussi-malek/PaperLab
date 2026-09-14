import { Sparkles } from 'lucide-react'
import type { ReactNode } from 'react'
import type { ChatSource } from '@/api/client'
import { pressable, slideUpIn } from '@/components/motion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { describeSource, type Segment } from './citations'

type Props = {
  question: string
  wholePaper: boolean
  /** In label order (C1, C2, …). An entry is null when a re-ingest replaced its chunk; the list is null until known. */
  sources: (ChatSource | null)[] | null
  segments: Segment[]
  /** Set once the answer is saved: the model label is only known then. */
  footer: { model: string; promptVersion: number } | null
  /** The saved answer's `llm_outputs` id; absent while it streams. */
  outputId?: string
  pending?: boolean
  /** Fade up on mount: only the answer being asked now, never ones loaded from history. */
  animate?: boolean
  /** Shows a source in the paper: the reader scrolls to its chunk and flashes it. */
  onCite: (source: ChatSource) => void
  /** Shown under the answer, e.g. an error with Retry. */
  children?: ReactNode
}

const CITE_HINT = 'The AI used this passage. Click to see it in the paper.'

export function ChatAnswer(props: Props) {
  const { question, wholePaper, sources, segments, footer, outputId, pending, animate, onCite, children } = props
  const sourceFor = (label: string) => sources?.find((source) => source?.label === label)
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
                    <Hint key={i} label={describeSource(source)} detail={CITE_HINT}>
                      <button
                        type="button"
                        className="chat-cite rounded-xs font-medium text-primary underline-offset-2 hover:underline"
                        aria-label={describeSource(source)}
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
              <AnswerMeta footer={footer} sources={sources} wholePaper={wholePaper} onCite={onCite} />
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

type MetaProps = Pick<Props, 'footer' | 'sources' | 'wholePaper' | 'onCite'>

/**
 * One quiet row: the AI mark, then a pill per source. Everything longer (the model, each passage's page and section)
 * waits in a tooltip, so a thread of answers doesn't repeat the same line under each one.
 */
function AnswerMeta({ footer, sources, wholePaper, onCite }: MetaProps) {
  const aiLabel = footer ? `AI · ${footer.model} · prompt v${footer.promptVersion}` : 'AI'
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
            sources.map(
              (source) =>
                source && (
                  <li key={source.label}>
                    <Hint label={describeSource(source)} detail={CITE_HINT}>
                      <Button
                        variant="outline"
                        size="xs"
                        className={cn('min-w-8 tabular-nums', pressable)}
                        aria-label={describeSource(source)}
                        onClick={() => onCite(source)}
                      >
                        {source.label}
                      </Button>
                    </Hint>
                  </li>
                ),
            )
          )}
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
