import { useState } from 'react'
import type { EligibilityUpdate, Hit } from '@/api/client'
import { useSearchHits, useSetEligibility, useSnowball } from '@/api/queries'
import { Button } from '@/components/ui/button'

/** Stage-2 (full-text) eligibility screening for papers already acquired via a search run (imported
 * automatically, or uploaded manually via ManualAcquisitionTab), plus one-hop snowballing from any of them.
 * Spec §9, §4 step 5.
 *
 * Both calls filter to `stage1_status: 'relevant'`, not just an `acquisition_status` — a hit only reaches
 * acquisition at all once stage-1 marks it relevant, but PRISMA's funnel (prisma_export's `sought`/`not_retrieved`/
 * `stage2_assessed`) counts stage-2 only for relevant hits too, so this list must match that scope exactly; without
 * it a hit stage-1 later un-marked "relevant" (still carrying acquisition_status imported/manual from before) would
 * keep showing up here for stage-2 screening while PRISMA no longer counts it at all.
 *
 * `useSearchHits` filters to exactly one `acquisition_status` per call, so this calls it twice — once for
 * 'imported', once for 'manual' — and merges the two `rows` arrays. Extending the hook/backend to accept a list
 * of statuses would be the bigger change for what only this one screen needs (Task 7's `queries.ts` guidance).
 *
 * Each call is independently keyset-paginated (50/page, same as ManualAcquisitionTab's identical situation —
 * see its "I7 fix 1" comment), so each gets its own "Load more" — silently showing only the first 50 imported
 * or first 50 manual papers would leave stage-2 screening incomplete with no indication anything is missing. */
export function ScreeningTab({ workspaceId }: { workspaceId: string }) {
  const imported = useSearchHits(workspaceId, 'relevant', 'imported')
  const manual = useSearchHits(workspaceId, 'relevant', 'manual')
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
          onSetEligibility={(paperId, runId, body) => setEligibility.mutate({ paperId, runId, body })}
          onSnowball={(paperId) => snowball.mutate({ seed_paper_ids: [paperId], backward: true, forward: true })}
          snowballPending={snowball.isPending}
        />
      ))}
      {imported.hasNextPage && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={imported.isFetchingNextPage}
          onClick={() => imported.fetchNextPage()}
        >
          {imported.isFetchingNextPage ? 'Loading…' : 'Load more imported'}
        </Button>
      )}
      {manual.hasNextPage && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={manual.isFetchingNextPage}
          onClick={() => manual.fetchNextPage()}
        >
          {manual.isFetchingNextPage ? 'Loading…' : 'Load more manual'}
        </Button>
      )}
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
 * Snowball.
 *
 * `HitOut.paper_id` is typed nullable (`string | null`), even though it should always be set for hits this tab
 * queries (`acquisition_status` 'imported'/'manual' only exist once a Paper row has been created — see
 * `useImportSearchHits`/`useUploadHitPdf` in queries.ts). Rather than force-unwrap it, this guards the actionable
 * section behind `paperId &&` — same convention as HitPreview's `hit.doi &&`/ManualAcquisitionTab's `hit.doi &&` —
 * so a hit with no linked paper record (however unlikely) renders no actions instead of firing a malformed
 * mutation call with `paperId: undefined`. */
function ScreeningRow({
  hit,
  onSetEligibility,
  onSnowball,
  snowballPending,
}: {
  hit: Hit
  onSetEligibility: (paperId: string, runId: string, body: EligibilityUpdate) => void
  onSnowball: (paperId: string) => void
  snowballPending: boolean
}) {
  const title = hit.title || hit.normalized_title
  const paperId = hit.paper_id
  const [excluding, setExcluding] = useState(false)
  const [reason, setReason] = useState('')

  const confirmExclude = (id: string) => {
    if (!reason) return
    onSetEligibility(id, hit.run_id, { status: 'exclude', exclude_reason: reason })
    setReason('')
    setExcluding(false)
  }

  return (
    <div className="flex items-center justify-between gap-3 border-b pb-2 text-sm">
      <span className="flex-1 truncate">{title}</span>
      <span className="text-xs text-muted-foreground">{hit.stage2_status ?? 'not assessed'}</span>
      {paperId ? (
        <>
          <Button
            type="button"
            size="sm"
            variant={hit.stage2_status === 'include' ? 'default' : 'outline'}
            onClick={() => onSetEligibility(paperId, hit.run_id, { status: 'include' })}
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
              <Button type="button" size="sm" variant="destructive" disabled={!reason} onClick={() => confirmExclude(paperId)}>
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
          <Button type="button" size="sm" variant="outline" disabled={snowballPending} onClick={() => onSnowball(paperId)}>
            Snowball
          </Button>
        </>
      ) : (
        <span className="text-xs text-muted-foreground">No linked paper record</span>
      )}
    </div>
  )
}
