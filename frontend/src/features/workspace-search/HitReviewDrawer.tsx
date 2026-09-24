import { useState } from 'react'
import { usePatchSearchHit } from '@/api/queries'
import { Button } from '@/components/ui/button'

const EXCLUDE_REASONS = ['wrong_topic', 'wrong_study_type', 'duplicate', 'language', 'inaccessible', 'other'] as const
type ExcludeReason = (typeof EXCLUDE_REASONS)[number]

/** Stage-1 triage for one hit: relevant/maybe close it outright, excluding requires picking a reason first —
 * the backend rejects `not_relevant` without one, so the button stays disabled until a reason is chosen. */
export function HitReviewDrawer({
  workspaceId,
  hitId,
  onClose,
}: {
  workspaceId: string
  hitId: string
  onClose: () => void
}) {
  const patch = usePatchSearchHit(workspaceId)
  const [reason, setReason] = useState<ExcludeReason | ''>('')

  const markNotRelevant = () => {
    if (!reason) return
    patch.mutate({ hitId, body: { stage1_status: 'not_relevant', stage1_exclude_reason: reason } }, { onSuccess: onClose })
  }

  return (
    <div role="dialog" aria-label="Review hit" className="fixed inset-y-0 right-0 w-80 border-l bg-background p-4">
      <div className="flex gap-2">
        <Button
          type="button"
          disabled={patch.isPending}
          onClick={() => patch.mutate({ hitId, body: { stage1_status: 'relevant' } }, { onSuccess: onClose })}
        >
          Relevant
        </Button>
        <Button
          type="button"
          disabled={patch.isPending}
          onClick={() => patch.mutate({ hitId, body: { stage1_status: 'maybe' } }, { onSuccess: onClose })}
        >
          Maybe
        </Button>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <select
          value={reason}
          onChange={(event) => setReason(event.target.value as ExcludeReason | '')}
          aria-label="Exclusion reason"
          className="h-8 flex-1 rounded-lg border bg-background px-2 text-sm"
        >
          <option value="">Select a reason…</option>
          {EXCLUDE_REASONS.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <Button type="button" variant="destructive" disabled={!reason || patch.isPending} onClick={markNotRelevant}>
          Not relevant
        </Button>
      </div>
      <Button type="button" variant="ghost" onClick={onClose} className="mt-4">
        Close
      </Button>
    </div>
  )
}
