import { Sparkles } from 'lucide-react'
import { useMemo } from 'react'
import type { Brief, ChatSource, Lens } from '@/api/client'
import { Alert, AlertAction, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { describeSource, splitCitations } from '@/features/chat/citations'
import { markdownPieces } from '@/features/chat/markdown'
import { renderPieces } from '@/features/chat/renderPieces'
import { ProvenanceBadge } from '@/features/notes/ProvenanceBadge'
import type { BriefStream } from './useBriefStream'

type Props = {
  lens: Lens
  /** The newest saved brief of this lens, or null. */
  saved: Brief | null
  stream: BriefStream
  onGenerate: () => void
  onCite: (source: ChatSource) => void
}

/**
 * The lens's AI brief (spec §5): Generate, then the streaming text, then the saved brief with its model and date, on
 * the opaque AI surface. Out of date once the lens's sections change; Regenerate writes a new one.
 */
export function BriefCard({ lens, saved, stream, onGenerate, onCite }: Props) {
  const mine = stream.lens === lens.id && stream.status !== 'idle'
  const failed = mine && stream.status === 'error' && stream.problem !== null
  // A failed brief that wrote nothing gives the card back to the saved one; the error sits above it.
  const live = mine && !(stream.status === 'done' && saved?.id === stream.outputId) && !(failed && saved && stream.segments.length === 0)
  const busy = live && (stream.status === 'sources' || stream.status === 'streaming')
  const content = live ? stream.segments.map((s) => (s.kind === 'text' ? s.text : `[${s.label}]`)).join('') : (saved?.content ?? '')
  const sources = live ? (stream.sources ?? []) : (saved?.sources ?? [])
  const pieces = useMemo(() => markdownPieces(content), [content])
  const known = new Set(sources.flatMap((source) => (source ? [source.label] : [])))
  const renderText = (text: string) =>
    splitCitations(text, known).map((segment, i) => {
      const source = segment.kind === 'cite' ? sources.find((candidate) => candidate?.label === segment.label) : undefined
      return source ? (
        <button
          key={i}
          type="button"
          className="brief-cite rounded-xs font-medium text-primary underline-offset-2 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={describeSource(source)}
          onClick={() => onCite(source)}
        >
          [{source.label}]
        </button>
      ) : (
        <span key={i}>{segment.kind === 'text' ? segment.text : `[${segment.label}]`}</span>
      )
    })

  if (!live && !saved) {
    return (
      <section aria-label={`${lens.label} brief`} className="brief-card flex flex-col items-start gap-2 rounded-2xl p-3.5 ring-1 ring-glass-border">
        <p className="text-sm text-muted-foreground">An AI summary of this lens, with citations to its passages.</p>
        <Button size="sm" onClick={onGenerate}>
          <Sparkles aria-hidden />
          Generate brief
        </Button>
      </section>
    )
  }
  return (
    // AI text sits on the opaque provenance surface, never on glass (D26).
    <section aria-label={`${lens.label} brief`} className="brief-card flex flex-col gap-2 rounded-2xl bg-provenance-llm-surface p-3.5">
      <header className="flex min-w-0 items-center gap-2">
        <ProvenanceBadge provenance="llm" />
        {!live && saved && (
          <span className="brief-meta truncate text-xs text-muted-foreground">
            {saved.model} · {new Date(saved.created_at).toLocaleDateString()}
          </span>
        )}
      </header>
      {failed && stream.problem && (
        <Alert variant="destructive" className="border-glass-border">
          <AlertDescription>{stream.problem.message}</AlertDescription>
          {stream.problem.retryable && (
            <AlertAction>
              <Button variant="outline" size="xs" onClick={onGenerate}>
                Retry
              </Button>
            </AlertAction>
          )}
        </Alert>
      )}
      {busy && content === '' ? (
        <p role="status" className="text-sm text-muted-foreground">
          Writing the brief…
        </p>
      ) : (
        <div className="brief-text space-y-2 text-sm leading-relaxed whitespace-pre-line">{renderPieces(pieces, renderText)}</div>
      )}
      {!live && saved?.partial && <p className="brief-partial text-xs text-muted-foreground">Based on part of this lens</p>}
      {!live && saved?.stale && (
        <div className="brief-stale flex items-center gap-2 text-sm">
          <span>Out of date: sections changed</span>
          <Button variant="outline" size="xs" onClick={onGenerate}>
            Regenerate
          </Button>
        </div>
      )}
    </section>
  )
}
