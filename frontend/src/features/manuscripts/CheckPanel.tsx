import { sileo } from 'sileo'
import { useState } from 'react'
import type { CheckRunResult } from '@/api/client'
import { useCheckBadge, useCheckList, useRunChecks } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { FindingRow } from './checks/FindingRow'
import { DoiCheck } from './DoiCheck'
import { badgeOf, groupByCheck, rowsOf, summary } from './checks/model'

type Props = { manuscriptId: string; savedTick: number; compiledAt: string | null | undefined; onJump: (file: string, line: number) => void }

export function CheckPanel({ manuscriptId, savedTick, compiledAt, onJump }: Props) {
  const badge = useCheckBadge(manuscriptId, compiledAt)
  const infos = useCheckList(manuscriptId)
  const run = useRunChecks()
  const [full, setFull] = useState<CheckRunResult | null>(null)
  const [lastTick, setLastTick] = useState<number | null>(null)

  const onCheck = () => {
    const tick = savedTick
    run.mutate(manuscriptId, {
      onSuccess: (r) => { setFull(r); setLastTick(tick) },
      onError: () => sileo.error({ title: "Couldn't run the checks" }),
    })
  }

  const tone = badgeOf(badge.data)
  const shown = full ?? badge.data
  const stale = full != null && lastTick !== savedTick
  const groups = shown ? groupByCheck(shown) : []
  const n = full?.ran.length ?? 0

  return (
    <section aria-label="Checks" className="shrink-0 border-t border-border bg-card/60 backdrop-blur">
      <div className="flex items-center gap-2 px-3 py-1.5">
        <h3 className="text-sm font-medium">Checks</h3>
        {badge.isError ? (
          <span aria-label="Quick problems" title="Couldn't refresh the quick checks" className="text-xs text-muted-foreground">?</span>
        ) : tone && (
          <span aria-label="Quick problems"
            className={cn('text-xs', tone.tone === 'error' && 'font-medium text-destructive', tone.tone === 'warning' && 'font-medium text-amber-700 dark:text-amber-500', tone.tone === 'clean' && 'text-muted-foreground')}>
            {tone.tone === 'clean' ? 'No quick problems' : tone.count}
          </span>
        )}
        <Button type="button" size="xs" variant="outline" className="ml-auto" disabled={run.isPending} aria-busy={run.isPending} onClick={onCheck}>
          {run.isPending ? 'Checking…' : 'Check'}
        </Button>
      </div>
      {run.isError && <p role="alert" className="px-3 pb-1 text-xs text-destructive">Couldn't run the checks. Try again.</p>}
      {stale && <p className="px-3 pb-1 text-xs text-muted-foreground">You've edited since this check. Press Check again.</p>}
      {(groups.length > 0 || (full && !full.findings.length)) && (
        <div className={cn('max-h-40 overflow-auto px-3 pb-2', run.isPending && 'opacity-60')}>
          {full && !full.findings.length && <p className="text-xs text-muted-foreground">Nothing found. {n} check{n === 1 ? '' : 's'} ran.</p>}
          {groups.map((g) => {
            const { rows, more } = rowsOf(g.findings)
            return (
              <div key={g.check} className="mt-1">
                <h4 className="text-xs font-medium">{infos.data?.find((i) => i.name === g.check)?.description ?? g.check}</h4>
                <p className="text-xs text-muted-foreground">{summary(g.counts)}</p>
                <ul className="mt-0.5 space-y-0.5">
                  {rows.map((x, i) => <FindingRow key={`${x.file}-${x.line}-${i}`} finding={x} onJump={onJump} />)}
                </ul>
                {more > 0 && <p className="mt-1 text-xs text-muted-foreground">and {more} more</p>}
              </div>
            )
          })}
        </div>
      )}
      <DoiCheck manuscriptId={manuscriptId} savedTick={savedTick} onJump={onJump} />
    </section>
  )
}
