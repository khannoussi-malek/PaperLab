import type { Hit } from '@/api/client'

/** The local model's suggestion for one hit (M31b): muted text, never a button or a colour-coded verdict — the
 * reader decides (spec §4.6). The note shows on hover. */
export function SuggestionChip({ hit }: { hit: Hit }) {
  if (!hit.suggestion) return null
  const text =
    hit.suggestion === 'unsure'
      ? 'Unsure'
      : hit.suggestion === 'exclude'
        ? `Suggests: exclude · ${(hit.suggestion_reason ?? 'other').replaceAll('_', ' ')}`
        : 'Suggests: include'
  return (
    <span title={hit.suggestion_note ?? undefined} className="shrink-0 rounded-full border px-1.5 py-0.5 text-xs text-muted-foreground">
      {text}
    </span>
  )
}
