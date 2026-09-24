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

/** `PrismaExportOut.runs` comes back as `Record<string, unknown>[]` — the backend returns `list[dict]` (see
 * `prisma_export` in `backend/app/core/workspace_search.py`), so openapi-typescript can't infer a precise shape.
 * This is the slice of each run dict's real keys the combined/per-run <select> actually needs. */
type PrismaRun = { id: string; query_text: string }

function asPrismaRuns(runs: PrismaExportOut['runs']): PrismaRun[] {
  return runs.map((r) => ({ id: String(r.id), query_text: String(r.query_text) }))
}

/** Read-only PRISMA funnel view: counts from `usePrismaExport`, combined across the workspace or scoped to one
 * run. Spec §13. */
export function PrismaTab({ workspaceId }: { workspaceId: string }) {
  const [runs, setRuns] = useState('all')
  const { data } = usePrismaExport(workspaceId, runs)

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
          {data && asPrismaRuns(data.runs).map((r) => (
            <option key={r.id} value={r.id}>{r.query_text}</option>
          ))}
        </select>
      </label>
      {data && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          {STAGES.map(([key, label]) => (
            <div key={key} className="contents">
              <dt className="text-muted-foreground">{label}</dt>
              <dd>{data[key]}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}
