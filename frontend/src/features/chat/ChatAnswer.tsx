import { Sparkles } from 'lucide-react'
import type { ReactNode } from 'react'
import type { ChatSource } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { Segment } from './citations'

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
  /** Shows a source in the paper: the reader scrolls to its chunk and flashes it. */
  onCite: (source: ChatSource) => void
  /** Shown under the answer, e.g. an error with Retry. */
  children?: ReactNode
}

const sourceName = (source: ChatSource) => [source.label, `p.${source.page}`, source.section].filter(Boolean).join(' · ')

export function ChatAnswer(props: Props) {
  const { question, wholePaper, sources, segments, footer, outputId, pending, onCite, children } = props
  const sourceFor = (label: string) => sources?.find((source) => source?.label === label)
  return (
    <article className="chat-answer flex flex-col gap-2" data-output-id={outputId}>
      <p className="chat-question self-end rounded-lg bg-glass-strong px-3 py-2 whitespace-pre-wrap ring-1 ring-glass-border">
        {question}
      </p>

      {(sources !== null || pending) && (
        // AI text sits on the opaque provenance surface, never on glass (D26).
        <div className="flex flex-col gap-2 rounded-lg bg-provenance-llm-surface p-3">
          {sources === null ? (
            <p className="text-sm text-muted-foreground">Finding sources…</p>
          ) : (
            <ul className="chat-sources flex flex-wrap gap-1" aria-label="Sources">
              {wholePaper ? (
                <li>
                  <Badge variant="outline">Whole paper · {sources.length} chunks</Badge>
                </li>
              ) : (
                sources.map(
                  (source) =>
                    source && (
                      <li key={source.label}>
                        <Button variant="outline" size="xs" onClick={() => onCite(source)}>
                          {sourceName(source)}
                        </Button>
                      </li>
                    ),
                )
              )}
            </ul>
          )}

          {/* The text content is exactly the answer, markers included: promote.ts counts offsets in it. */}
          <p className="chat-answer-text whitespace-pre-wrap">
            {segments.map((segment, i) => {
              const source = segment.kind === 'cite' ? sourceFor(segment.label) : undefined
              return source ? (
                <button
                  key={i}
                  type="button"
                  className="chat-cite rounded-xs font-medium text-primary underline-offset-2 hover:underline"
                  aria-label={`Source ${sourceName(source)}`}
                  onClick={() => onCite(source)}
                >
                  [{source.label}]
                </button>
              ) : (
                <span key={i}>{segment.kind === 'text' ? segment.text : `[${segment.label}]`}</span>
              )
            })}
          </p>

          {footer && (
            <p className="chat-answer-footer flex items-center gap-1 text-xs text-muted-foreground">
              <Sparkles aria-hidden className="size-3" />
              AI · {footer.model} · prompt v{footer.promptVersion}
            </p>
          )}
        </div>
      )}
      {children}
    </article>
  )
}
