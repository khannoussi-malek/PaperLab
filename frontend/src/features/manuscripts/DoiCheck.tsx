import { sileo } from 'sileo'
import { useState } from 'react'
import { ApiError, type CheckFinding, type DoiCheckResult } from '@/api/client'
import { useDoiCheck } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { Severity } from './checks/model'

type Props = { manuscriptId: string; savedTick: number; onJump: (file: string, line: number) => void }

const DOT: Record<Severity, string> = { error: 'bg-destructive', warning: 'bg-amber-500', info: 'bg-muted-foreground' }
const ROW = 'flex w-full items-baseline justify-between gap-3 rounded px-1 py-0.5 text-left text-sm'

// A copy of CheckPanel's local Row (it is not exported).
function Row({ finding: x, onJump }: { finding: CheckFinding; onJump: Props['onJump'] }) {
  const inner = (
    <>
      <span className="flex items-baseline gap-1.5">
        <span aria-hidden className={cn('size-1.5 shrink-0 rounded-full', DOT[x.severity])} />
        <span className="text-xs text-muted-foreground">{x.severity}</span>
        <span>{x.message}</span>
      </span>
      {x.file != null && x.line != null && <span className="shrink-0 text-xs text-muted-foreground">{x.file}:{x.line}</span>}
    </>
  )
  const { file, line } = x
  return (
    <li>
      {file != null && line != null ? (
        <button type="button" onClick={() => onJump(file, line)}
          className={cn(ROW, 'hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring')}>{inner}</button>
      ) : <div className={ROW}>{inner}</div>}
      {x.fix_hint && <p className="pl-4 text-xs text-muted-foreground">{x.fix_hint}</p>}
    </li>
  )
}

function verdict(r: DoiCheckResult): string {
  if (r.checked === 0) return 'No DOIs found in your .bib files.'
  const all = r.checked === 1 ? 'All 1 DOI resolves.' : `All ${r.checked} DOIs resolve.`
  return r.not_checked > 0 ? `${all} ${r.not_checked} not checked (limit reached).` : all
}

export function DoiCheck({ manuscriptId, savedTick, onJump }: Props) {
  const run = useDoiCheck()
  const [result, setResult] = useState<DoiCheckResult | null>(null)
  const [lastTick, setLastTick] = useState<number | null>(null)

  const onCheck = () => {
    const tick = savedTick
    run.mutate(manuscriptId, {
      onSuccess: (r) => { setResult(r); setLastTick(tick) },
      onError: (e) => { if (!(e instanceof ApiError && e.code === 'crossref_disabled')) sileo.error({ title: "Couldn't check the DOIs" }) },
    })
  }

  const off = run.error instanceof ApiError && run.error.code === 'crossref_disabled'
  const stale = result != null && lastTick !== savedTick

  return (
    <div className="border-t border-border/60 px-3 py-1.5">
      <div className="flex items-center gap-2">
        <p className="text-xs text-muted-foreground">Sends only the DOI of each reference in your .bib files to Crossref, which paces anonymous requests, so a long list takes a while. Nothing else leaves your computer.</p>
        <Button type="button" size="xs" variant="outline" className="ml-auto shrink-0" disabled={run.isPending} aria-busy={run.isPending} onClick={onCheck}>
          {run.isPending ? 'Checking DOIs…' : 'Check DOIs online'}
        </Button>
      </div>
      {run.isError && (
        <p role="alert" className="pt-1 text-xs text-destructive">
          {off ? 'Crossref is turned off in Settings → Paper sources.' : "Couldn't reach Crossref. Try again."}
        </p>
      )}
      {stale && <p className="pt-1 text-xs text-muted-foreground">You've edited since this check. Press again.</p>}
      {result && (
        <div className={cn('pt-1', run.isPending && 'opacity-60')}>
          {!result.findings.length && <p className="text-xs text-muted-foreground">{verdict(result)}</p>}
          <ul className="space-y-0.5">
            {result.findings.map((x, i) => <Row key={`${x.file}-${x.line}-${i}`} finding={x} onJump={onJump} />)}
          </ul>
        </div>
      )}
    </div>
  )
}
