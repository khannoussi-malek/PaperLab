import { cn } from '@/lib/utils'

// Reuses the exact tokens the stage1/stage2 action buttons already use for these same statuses (HitPreview's
// "Relevant"/"Not relevant" buttons, ScreeningRow's "Include"/"Exclude") — no new color invented. 'maybe' and
// null (unreviewed/not assessed) stay neutral: neither button has a strong color for those either.
const TONES: Record<string, string> = {
  relevant: 'bg-primary',
  include: 'bg-primary',
  not_relevant: 'bg-destructive',
  exclude: 'bg-destructive',
}

/** A small color dot beside a stage1/stage2 status label, so a long list can be scanned by color instead of read
 * word by word. The text stays the source of truth — color is never the only signal (a11y). */
export function StatusDot({ status }: { status: string | null }) {
  const tone = status ? TONES[status] : undefined
  return (
    <span
      aria-hidden
      className={cn('inline-block size-1.5 shrink-0 rounded-full', tone ?? 'border border-muted-foreground/50')}
    />
  )
}
