import { ClipboardList } from 'lucide-react'
import { useState } from 'react'
import { usePrismaExport } from '@/api/queries'
import type { PrismaExportOut } from '@/api/client'
import { LoadError } from '@/features/library/ErrorAlert'
import { Badge } from '@/components/ui/badge'
import { Term } from '@/features/workspaces/Term'
import type { GlossaryKey } from '@/features/workspaces/glossary'
import { reasonLabel } from './hitReview'
import { EmptyState, GoToSearchAction, TabSkeleton } from '@/features/workspaces/TabStates'
import { asPrismaRunMeta } from './prismaRunMeta'

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

// PRISMA's own flow-diagram phases, so the funnel reads as the methodology a systematic-review author already
// knows, not an arbitrary 9-row table.
type Row = [StageKey, string, GlossaryKey | null]
const PHASES: [string, GlossaryKey | null, Row[]][] = [
  [
    'Identification',
    null,
    [
      ['identified', 'Identified', 'identified'],
      ['duplicates_removed', 'Duplicates removed', 'duplicatesRemoved'],
    ],
  ],
  [
    'Screening',
    null,
    [
      ['stage1_screened', 'Screened on title & abstract', 'titleAbstract'],
      ['stage1_excluded', 'Excluded on title & abstract', 'titleAbstract'],
    ],
  ],
  [
    'Eligibility',
    'eligibility',
    [
      ['sought', 'Reports sought', 'reportsSought'],
      ['not_retrieved', 'Not retrieved', 'notRetrieved'],
      ['stage2_assessed', 'Full texts assessed', 'fullText'],
      ['stage2_excluded', 'Excluded after full text', 'fullText'],
    ],
  ],
  ['Included', null, [['included', 'Included', null]]],
]

// A stage whose count has a reason breakdown (spec §13): reason -> count, straight off PrismaExportOut, no
// separate fetch.
const REASON_FIELD: Partial<Record<StageKey, 'stage1_excluded_by_reason' | 'stage2_excluded_by_reason'>> = {
  stage1_excluded: 'stage1_excluded_by_reason',
  stage2_excluded: 'stage2_excluded_by_reason',
}

/** Read-only PRISMA funnel view: counts from `usePrismaExport`, combined across the workspace or scoped to one
 * run. Spec §13. */
export function PrismaTab({ workspaceId, runId }: { workspaceId: string; runId?: string | null }) {
  const [runs, setRuns] = useState('all')
  const { data, isPending, isError, error, refetch } = usePrismaExport(workspaceId, runs)
  // Dropdown options (and the selected run's own query/filters/date below) always come from the combined
  // export — the backend only populates `runs` on that branch ([] for a per-run export, since the caller already
  // knows which run). Fetched separately so the picker stays populated after selecting one run; this shares the
  // 'all' query's cache entry when `runs === 'all'`, so no extra request.
  const { data: allRunsData } = usePrismaExport(workspaceId, 'all')
  const allRuns = allRunsData ? asPrismaRunMeta(allRunsData.runs) : []
  const selectedRun = runs !== 'all' ? allRuns.find((r) => r.id === runs) : undefined
  // Nothing searched yet: a funnel of zeros says nothing, so show the next step instead.
  const empty = !!data && !!allRunsData && allRuns.length === 0 && data.identified === 0

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
      {!empty && (
      <label className="flex w-fit items-center gap-2 text-sm">
        <span>Runs</span>
        <select
          value={runs}
          onChange={(e) => setRuns(e.target.value)}
          className="w-fit rounded-md border border-input bg-background px-2 py-1 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <option value="all">All runs (combined)</option>
          {allRuns.map((r) => (
            <option key={r.id} value={r.id}>{r.query_text}</option>
          ))}
        </select>
      </label>
      )}
      {selectedRun && (
        <dl
          aria-label="Selected run details"
          className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-lg border bg-muted/30 p-3 text-sm"
        >
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
      {isPending && <TabSkeleton label="Loading PRISMA report" />}
      {empty && (
        <EmptyState title="Your PRISMA flow will appear here" action={<GoToSearchAction workspaceId={workspaceId} runId={runId} />}>
          It fills in as you search and screen.
        </EmptyState>
      )}
      {isError && <LoadError message={error.message} onRetry={() => void refetch()} />}
      {data && !empty && (
        <div className="flex flex-col gap-3 rounded-lg border p-3">
          {PHASES.map(([phase, phaseTerm, stages]) => (
            <div key={phase} className="flex flex-col gap-1.5">
              {stages.length > 1 && (
                <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{phaseTerm ? <Term term={phaseTerm}>{phase}</Term> : phase}</h4>
              )}
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
                {stages.map(([key, label, term]) => (
                  <div key={key} className="contents">
                    <dt className="text-muted-foreground">{term ? <Term term={term}>{label}</Term> : label}</dt>
                    <dd className="flex flex-wrap items-center gap-1.5">
                      <span className="tabular-nums">{data[key]}</span>
                      <ReasonBreakdown reasons={reasonBreakdown(data, key)} />
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
      )}
      {data && !empty && (data.automation.length > 0 || (data.notes ?? []).length > 0 || data.screening_criteria) && (
        <section aria-label="Methods notes" className="flex flex-col gap-2 rounded-lg border p-3 text-sm">
          <h3 className="flex items-center gap-1.5 font-medium">
            <ClipboardList aria-hidden className="size-4" />
            Methods notes
          </h3>
          {data.screening_criteria && (
            <div>
              <div className="text-muted-foreground">Eligibility criteria</div>
              <p className="whitespace-pre-wrap">{data.screening_criteria}</p>
            </div>
          )}
          {[...data.automation, ...(data.notes ?? [])].map((line) => (
            <p key={line} className="text-muted-foreground">
              {line}
            </p>
          ))}
        </section>
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
    <>
      {Object.entries(reasons).map(([reason, count]) => (
        <Badge key={reason} variant="outline" className="font-normal text-muted-foreground">
          {reasonLabel(reason)}: {count}
        </Badge>
      ))}
    </>
  )
}
