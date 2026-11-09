import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { ProvNode } from '@/api/client'
import { refreshTree, usePatchSearchHit, useSetBranch } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { EXCLUDE_REASONS, reasonLabel } from '@/features/workspace-search/hitReview'
import type { BranchTarget } from '../BranchControl'
import type { Grab } from './useGrab'

const BOTH = ['cites', 'cited_by']

type Props = { workspaceId: string; node: ProvNode; target: BranchTarget | null; isHit: boolean; grab: Grab; pending: boolean; onReveal: () => void }

/** Include / Exclude (screening) and Go further / Stop here (branch) for the paper on the card. None of them moves the walk. */
export function Decisions({ workspaceId, node, target, isHit, grab, pending, onReveal }: Props) {
  const client = useQueryClient()
  const patch = usePatchSearchHit(workspaceId)
  const setBranch = useSetBranch(workspaceId)
  const [excludeReason, setExcludeReason] = useState('')
  const [reason, setReason] = useState(node.branch?.reason ?? '')
  const state = node.branch?.state
  const refresh = { onSuccess: () => refreshTree(client, workspaceId) }

  const goFurther = async () => {
    if (!target) return
    try {
      await setBranch.mutateAsync({ ...target, state: 'go_further', directions: BOTH, reason: null })
    } catch { return } // the error shows below; do not grab for a branch that was not saved
    const missing = BOTH.filter((d) => !node.snowballed.includes(d))
    if (!missing.length) return onReveal() // nothing to fetch: still show the owner where the next papers are
    if (await grab(node.id, target, { backward: missing.includes('cites'), forward: missing.includes('cited_by') })) onReveal()
  }
  const stop = (text: string | null) => target && setBranch.mutate({ ...target, state: 'stopped', directions: [], reason: text })
  const pressed = (on: boolean) => ({ 'aria-pressed': on, variant: on ? ('default' as const) : ('outline' as const) })

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {isHit && (
          <>
            <Button type="button" size="sm" {...pressed(node.decision === 'relevant')} onClick={() => patch.mutate({ hitId: node.id, body: { stage1_status: 'relevant' } }, refresh)}>Include</Button>
            <select aria-label="Exclusion reason" value={excludeReason} onChange={(e) => setExcludeReason(e.target.value)} className="h-7 rounded-lg border bg-background px-2 text-xs">
              <option value="">Reason…</option>
              {EXCLUDE_REASONS.map((r) => <option key={r} value={r}>{reasonLabel(r)}</option>)}
            </select>
            <Button type="button" size="sm" {...pressed(node.decision === 'not_relevant')} disabled={!excludeReason && node.decision !== 'not_relevant'}
              onClick={() => excludeReason && patch.mutate({ hitId: node.id, body: { stage1_status: 'not_relevant', stage1_exclude_reason: excludeReason as (typeof EXCLUDE_REASONS)[number] } }, refresh)}>
              Exclude
            </Button>
          </>
        )}
        {target && (
          <>
            <Button type="button" size="sm" {...pressed(state === 'go_further')} disabled={pending || setBranch.isPending} onClick={goFurther}>Go further</Button>
            {pending && <span role="status" className="text-xs text-muted-foreground">Snowballing…</span>}
            <Button type="button" size="sm" {...pressed(state === 'stopped')} onClick={() => stop(reason.trim() || null)}>Stop here</Button>
          </>
        )}
      </div>
      {state === 'stopped' && (
        <label className="block text-xs">
          Reason
          <input className="mt-1 block w-full rounded-md border border-border bg-background px-2 py-1 text-sm" maxLength={200} value={reason} placeholder="e.g. too general"
            onChange={(e) => setReason(e.target.value)} onBlur={() => stop(reason.trim() || null)} onKeyDown={(e) => e.key === 'Enter' && stop(reason.trim() || null)} />
        </label>
      )}
      {(patch.isError || setBranch.isError) && <p role="alert" className="text-xs text-destructive">{(patch.error ?? setBranch.error)?.message}</p>}
    </div>
  )
}
