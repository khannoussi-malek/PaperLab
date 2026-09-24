import { useState } from 'react'
import { usePrismaExport } from '@/api/queries'
import type { PrismaExportOut } from '@/api/client'

type StageKey =
  | 'identified'
  | 'duplicates_removed'
  | 'stage1_screened'
  | 'stage1_excluded'
  | 'sought'
  | 'not_retrieved'
  | 'stage2_assessed'
  | 'stage2_excluded'
  | 'included'

const STAGES: [StageKey, string][] = [
  ['identified', 'Identified'],
  ['duplicates_removed', 'Duplicates removed'],
  ['stage1_screened', 'Stage-1 screened'],
  ['stage1_excluded', 'Stage-1 excluded'],
  ['sought', 'Reports sought'],
  ['not_retrieved', 'Not retrieved'],
  ['stage2_assessed', 'Stage-2 assessed'],
  ['stage2_excluded', 'Stage-2 excluded'],
  ['included', 'Included'],
]

// A stage whose count has a reason breakdown (spec §13): reason -> count, straight off PrismaExportOut, no
// separate fetch.
const REASON_FIELD: Partial<Record<StageKey, 'stage1_excluded_by_reason' | 'stage2_excluded_by_reason'>> = {
  stage1_excluded: 'stage1_excluded_by_reason',
  stage2_excluded: 'stage2_excluded_by_reason',
}

/** `PrismaExportOut.runs` comes back as `Record<string, unknown>[]` — the backend returns `list[dict]` (see
 * `prisma_export` in `backend/app/core/prisma_export.py`), so openapi-typescript can't infer a precise shape.
 * This is the slice of each run dict's real keys the combined/per-run <select> and the per-run detail panel
 * below actually need. */
type PrismaRunMeta = { id: string; query_text: string; filters_json: Record<string, unknown>; started_at: string }

function asPrismaRunMeta(runs: PrismaExportOut['runs']): PrismaRunMeta[] {
  return runs.map((r) => ({
    id: String(r.id),
    query_text: String(r.query_text),
    filters_json: (r.filters_json as Record<string, unknown> | undefined) ?? {},
    started_at: String(r.started_at),
  }))
}

/** Read-only PRISMA funnel view: counts from `usePrismaExport`, combined across the workspace or scoped to one
 * run. Spec §13. */
export function PrismaTab({ workspaceId }: { workspaceId: string }) {
  const [runs, setRuns] = useState('all')
  const { data, isPending, isError, error } = usePrismaExport(workspaceId, runs)
  // Dropdown options (and the selected run's own query/filters/date below) always come from the combined
  // export — the backend only populates `runs` on that branch ([] for a per-run export, since the caller already
  // knows which run). Fetched separately so the picker stays populated after selecting one run; this shares the
  // 'all' query's cache entry when `runs === 'all'`, so no extra request.
  const { data: allRunsData } = usePrismaExport(workspaceId, 'all')
  const allRuns = allRunsData ? asPrismaRunMeta(allRunsData.runs) : []
  const selectedRun = runs !== 'all' ? allRuns.find((r) => r.id === runs) : undefined

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
      <label className="flex w-fit items-center gap-2 text-sm">
        <span>Runs</span>
        <select
          value={runs}
          onChange={(e) => setRuns(e.target.value)}
          className="w-fit rounded border px-2 py-1 text-sm"
        >
          <option value="all">All runs (combined)</option>
          {allRuns.map((r) => (
            <option key={r.id} value={r.id}>{r.query_text}</option>
          ))}
        </select>
      </label>
      {selectedRun && (
        <dl aria-label="Selected run details" className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-muted-foreground">Query</dt>
          <dd>{selectedRun.query_text}</dd>
          <dt className="text-muted-foreground">Filters</dt>
          <dd>
            {Object.keys(selectedRun.filters_json).length > 0 ? JSON.stringify(selectedRun.filters_json) : 'None'}
          </dd>
          <dt className="text-muted-foreground">Date</dt>
          <dd>{selectedRun.started_at}</dd>
        </dl>
      )}
      {isPending && <p className="text-sm text-muted-foreground">Loading…</p>}
      {isError && (
        <p role="alert" className="text-xs text-destructive">
          {error.message}
        </p>
      )}
      {data && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          {STAGES.map(([key, label]) => (
            <div key={key} className="contents">
              <dt className="text-muted-foreground">{label}</dt>
              <dd>
                {data[key]}
                <ReasonBreakdown reasons={reasonBreakdown(data, key)} />
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}

function reasonBreakdown(data: PrismaExportOut, key: StageKey): Record<string, number> | null {
  const field = REASON_FIELD[key]
  return field ? data[field] : null
}

function ReasonBreakdown({ reasons }: { reasons: Record<string, number> | null }) {
  if (!reasons || Object.keys(reasons).length === 0) return null
  return (
    <ul className="mt-1 list-disc pl-4 text-xs text-muted-foreground">
      {Object.entries(reasons).map(([reason, count]) => (
        <li key={reason}>
          {reason}: {count}
        </li>
      ))}
    </ul>
  )
}
