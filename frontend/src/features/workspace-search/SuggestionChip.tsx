import type { Hit } from '@/api/client'
import { Badge } from '@/components/ui/badge'

/** The local model's suggestion for one hit (M31b): a muted outline badge, the same visual language as the
 * "Found by" source badges on a search result (`CandidateList`) — informational, never a button or a
 * colour-coded verdict. The reader decides (spec §4.6). The note shows on hover. */
export function SuggestionChip({ hit }: { hit: Hit }) {
  if (!hit.suggestion) return null
  const text =
    hit.suggestion === 'unsure'
      ? 'Unsure'
      : hit.suggestion === 'exclude'
        ? `Suggests: exclude · ${(hit.suggestion_reason ?? 'other').replaceAll('_', ' ')}`
        : 'Suggests: include'
  return (
    <Badge
      variant="outline"
      title={hit.suggestion_note ?? undefined}
      className="shrink-0 font-normal text-muted-foreground"
    >
      {text}
    </Badge>
  )
}
