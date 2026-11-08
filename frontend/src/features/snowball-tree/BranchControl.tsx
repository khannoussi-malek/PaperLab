import { useEffect, useState } from 'react'
import type { BranchIn, ProvBranch } from '@/api/client'
import { useSetBranch } from '@/api/queries'
import { Button } from '@/components/ui/button'

export type BranchTarget = { hit_id: string } | { paper_id: string }
const BOTH = ['cites', 'cited_by']
const DIRECTION_LABEL: Record<string, string> = { cites: 'Its references', cited_by: 'Papers citing it' }

/** Go further / Stop here / Undecided for one node. Each click saves at once. */
export function BranchControl({ workspaceId, target, branch }: { workspaceId: string; target: BranchTarget; branch?: ProvBranch | null }) {
  const set = useSetBranch(workspaceId)
  const [state, setState] = useState<string | null>(branch?.state ?? null)
  const [directions, setDirections] = useState<string[]>(branch?.state === 'go_further' ? branch.directions : BOTH)
  const [reason, setReason] = useState(branch?.reason ?? '')
  const fromServer = () => {
    setState(branch?.state ?? null)
    setDirections(branch?.state === 'go_further' ? branch.directions : BOTH)
    setReason(branch?.reason ?? '')
  }
  useEffect(fromServer, [branch?.state, branch?.directions, branch?.reason]) // eslint-disable-line react-hooks/exhaustive-deps

  // A failed save puts the buttons back to what the server holds.
  const save = (body: Pick<BranchIn, 'state' | 'directions' | 'reason'>) =>
    set.mutate({ ...target, ...body }, { onError: fromServer })
  const goFurther = (next: string[]) => {
    setDirections(next)
    save({ state: 'go_further', directions: next, reason: null })
  }
  const toggle = (d: string) => {
    const next = BOTH.filter((k) => (k === d ? !directions.includes(k) : directions.includes(k)))
    if (next.length) goFurther(next)
  }
  const choose = (next: string | null) => {
    setState(next)
    if (next === 'go_further') goFurther(directions)
    else save({ state: next, directions: [], reason: null })
  }
  const button = (label: string, value: string | null) => (
    <Button type="button" size="sm" variant={state === value ? 'default' : 'outline'} aria-pressed={state === value} onClick={() => choose(value)}>
      {label}
    </Button>
  )

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {button('Go further', 'go_further')}
        {button('Stop here', 'stopped')}
        {button('Undecided', null)}
      </div>
      {state === 'go_further' &&
        BOTH.map((d) => (
          <label key={d} className="flex items-center gap-2 text-xs">
            <input type="checkbox" checked={directions.includes(d)} onChange={() => toggle(d)} />
            {DIRECTION_LABEL[d]}
          </label>
        ))}
      {state === 'stopped' && (
        <form onSubmit={(e) => { e.preventDefault(); save({ state: 'stopped', directions: [], reason: reason.trim() || null }) }}>
          <label className="block text-xs">
            Reason
            <input
              className="mt-1 block w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
              maxLength={200}
              value={reason}
              placeholder="e.g. too general"
              onChange={(e) => setReason(e.target.value)}
              onBlur={() => save({ state: 'stopped', directions: [], reason: reason.trim() || null })}
            />
          </label>
        </form>
      )}
      {set.isError && <p role="alert" className="text-xs text-destructive">{set.error.message}</p>}
    </div>
  )
}
