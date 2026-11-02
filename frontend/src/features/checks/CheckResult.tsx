import { CircleAlert, CircleCheck, CircleDashed, Sparkles } from 'lucide-react'
import type { ReactNode } from 'react'
import type { ChatSource } from '@/api/client'
import { slideUpIn } from '@/components/motion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { describeSource, splitCitations } from '@/features/chat/citations'
import { cn } from '@/lib/utils'
import type { CheckLine } from './exitTest'

const VERDICT: Record<CheckLine['verdict'], { word: string; icon: ReactNode }> = {
  missing: { word: 'Missing', icon: <CircleDashed aria-hidden /> },
  unsupported: { word: 'Unsupported', icon: <CircleAlert aria-hidden /> },
  supported: { word: 'Supported', icon: <CircleCheck aria-hidden /> },
}

type Props = {
  label: string
  lines: CheckLine[]
  dropped: number
  sources: (ChatSource | null)[]
  /** The AI mark's words: model, prompt version and what was read. */
  tooltip: string
  stale: boolean
  busy: boolean
  onCheckAgain: () => void
  onCite: (source: ChatSource) => void
}

/** A check's lines. It names gaps only: there is nothing to save, copy or insert here (D118). */
export function CheckResult({ label, lines, dropped, sources, tooltip, stale, busy, onCheckAgain, onCite }: Props) {
  const known = new Set(sources.flatMap((source) => (source ? [source.label] : [])))
  const sourceFor = (cite: string) => sources.find((source) => source?.label === cite)
  const allDropped = lines.length === 0 && dropped > 0
  const cite = (text: string) =>
    splitCitations(text, known).map((segment, i) => {
      const source = segment.kind === 'cite' ? sourceFor(segment.label) : undefined
      if (segment.kind === 'text') return <span key={i}>{segment.text}</span>
      if (!source) return <span key={i}>[{segment.label}]</span>
      return (
        <button
          key={i}
          type="button"
          className="check-cite rounded-xs font-medium text-primary underline-offset-2 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={describeSource(source)}
          onClick={() => onCite(source)}
        >
          [{source.label}]
        </button>
      )
    })
  return (
    <section
      aria-label={`Check of your ${label}`}
      className={cn('check-result flex flex-col gap-2 rounded-2xl bg-provenance-llm-surface p-3.5', slideUpIn, stale && 'opacity-70')}
    >
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <span tabIndex={0} className="flex size-6 items-center justify-center rounded-full text-provenance-llm outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <Sparkles aria-hidden className="size-3.5" />
                <span className="sr-only">{tooltip}</span>
              </span>
            </TooltipTrigger>
            <TooltipContent>{tooltip}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
        Check
      </div>
      {lines.length === 0 && dropped === 0 && <p className="text-sm">No gaps found in the passages it read.</p>}
      {lines.length > 0 && (
        <ul className="flex flex-col gap-2">
          {lines.map((line, i) => (
            <li key={i} className="check-line flex flex-col items-start gap-1 text-sm" data-verdict={line.verdict}>
              <Badge variant="outline" className="gap-1">
                {VERDICT[line.verdict].icon}
                {VERDICT[line.verdict].word}
              </Badge>
              <span>{cite(line.text)}</span>
            </li>
          ))}
        </ul>
      )}
      {allDropped ? (
        <p className="check-dropped text-sm">The reply didn't follow the check's format, so nothing is shown. Check again, or pick another model in Chat.</p>
      ) : (
        dropped > 0 && (
          <p className="check-dropped text-xs text-muted-foreground">
            {dropped === 1
              ? "1 line of the reply didn't follow the check's format and was left out."
              : `${dropped} lines of the reply didn't follow the check's format and were left out.`}
          </p>
        )
      )}
      {stale && <p className="check-stale text-sm">Out of date: you changed this note after the check.</p>}
      <Button variant={stale ? 'default' : 'ghost'} size="sm" className="self-start" disabled={busy} onClick={onCheckAgain}>
        Check again
      </Button>
    </section>
  )
}
