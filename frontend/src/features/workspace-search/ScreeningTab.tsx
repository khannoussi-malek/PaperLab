import { useState } from 'react'
import type { Hit } from '@/api/client'
import { useSearchHits, useSetEligibility, useSnowball } from '@/api/queries'
import { Button } from '@/components/ui/button'

/** Stage-2 (full-text) eligibility screening for papers already acquired via a search run (imported
 * automatically, or uploaded manually via ManualAcquisitionTab), plus one-hop snowballing from any of them.
 * Spec §9, §4 step 5.
 *
 * `useSearchHits` filters to exactly one `acquisition_status` per call, so this calls it twice — once for
 * 'imported', once for 'manual' — and merges the two `rows` arrays. Extending the hook/backend to accept a list
 * of statuses would be the bigger change for what only this one screen needs (Task 7's `queries.ts` guidance). */
export function ScreeningTab({ workspaceId }: { workspaceId: string }) {
  const imported = useSearchHits(workspaceId, undefined, 'imported')
  const manual = useSearchHits(workspaceId, undefined, 'manual')
  const setEligibility = useSetEligibility(workspaceId)
  const snowball = useSnowball(workspaceId)

  const rows = [
    ...(imported.data?.pages.flatMap((page) => page.items) ?? []),
    ...(manual.data?.pages.flatMap((page) => page.items) ?? []),
  ]

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 p-3">
      {rows.length === 0 && (
        <p className="text-sm text-muted-foreground">Nothing to screen yet — import or upload a paper first.</p>
      )}
      {rows.map((hit) => (
        <ScreeningRow
          key={hit.id}
          hit={hit}
          onInclude={() =>
            setEligibility.mutate({ paperId: hit.paper_id!, runId: hit.run_id, body: { status: 'include' } })
          }
          onExclude={(reason) =>
            setEligibility.mutate({
              paperId: hit.paper_id!,
              runId: hit.run_id,
              body: { status: 'exclude', exclude_reason: reason },
            })
          }
          onSnowball={() => snowball.mutate({ seed_paper_ids: [hit.paper_id!], backward: true, forward: true })}
          snowballPending={snowball.isPending}
        />
      ))}
      {setEligibility.isError && (
        <p role="alert" className="text-xs text-destructive">
          {setEligibility.error.message}
        </p>
      )}
      {snowball.isError && (
        <p role="alert" className="text-xs text-destructive">
          {snowball.error.message}
        </p>
      )}
      {snowball.isSuccess && (
        <p role="status" className="text-xs text-muted-foreground">
          {snowballMessage(snowball.data)}
        </p>
      )}
    </div>
  )
}

function snowballMessage(result: { new_hits: number; skipped_seeds: string[]; errors: Record<string, string> }) {
  const parts = [
    result.new_hits > 0 ? `Found ${result.new_hits} new paper${result.new_hits === 1 ? '' : 's'}.` : 'No new papers found.',
  ]
  if (result.skipped_seeds.length > 0) {
    parts.push(`Skipped ${result.skipped_seeds.length} seed(s) with no Semantic Scholar match.`)
  }
  const errorMessages = Object.values(result.errors)
  if (errorMessages.length > 0) parts.push(errorMessages.join(' '))
  return parts.join(' ')
}

/** One hit's row: verdict badge, Include, a two-step free-text Exclude (stage-2's `stage2_exclude_reason` has no
 * CHECK constraint in the DB, unlike stage-1's fixed `EXCLUDE_REASONS` enum — so this is a plain text input, not a
 * `<select>`, gated the same way HitPreview's stage-1 "Not relevant" button gates on `disabled={!reason}`), and
 * Snowball. */
function ScreeningRow({
  hit,
  onInclude,
  onExclude,
  onSnowball,
  snowballPending,
}: {
  hit: Hit
  onInclude: () => void
  onExclude: (reason: string) => void
  onSnowball: () => void
  snowballPending: boolean
}) {
  const title = hit.title || hit.normalized_title
  const [excluding, setExcluding] = useState(false)
  const [reason, setReason] = useState('')

  const confirmExclude = () => {
    if (!reason) return
    onExclude(reason)
    setReason('')
    setExcluding(false)
  }

  return (
    <div className="flex items-center justify-between gap-3 border-b pb-2 text-sm">
      <span className="flex-1 truncate">{title}</span>
      <span className="text-xs text-muted-foreground">{hit.stage2_status ?? 'not assessed'}</span>
      <Button
        type="button"
        size="sm"
        variant={hit.stage2_status === 'include' ? 'default' : 'outline'}
        onClick={onInclude}
      >
        Include
      </Button>
      {excluding ? (
        <>
          <label htmlFor={`exclude-reason-${hit.id}`} className="sr-only">
            Exclusion reason for {title}
          </label>
          <input
            id={`exclude-reason-${hit.id}`}
            type="text"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Reason for excluding…"
            className="h-8 w-40 rounded-lg border bg-background px-2 text-sm"
          />
          <Button type="button" size="sm" variant="destructive" disabled={!reason} onClick={confirmExclude}>
            Confirm exclude
          </Button>
        </>
      ) : (
        <Button
          type="button"
          size="sm"
          variant={hit.stage2_status === 'exclude' ? 'destructive' : 'outline'}
          onClick={() => setExcluding(true)}
        >
          Exclude
        </Button>
      )}
      <Button type="button" size="sm" variant="outline" disabled={snowballPending} onClick={onSnowball}>
        Snowball
      </Button>
    </div>
  )
}
