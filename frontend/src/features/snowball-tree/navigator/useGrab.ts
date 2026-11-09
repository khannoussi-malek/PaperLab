import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { refreshTree, useSnowball } from '@/api/queries'
import { friendlySnowballError } from '@/features/workspace-search/snowballText'
import type { BranchTarget } from '../BranchControl'

export type GrabState = { status: 'pending' } | { status: 'done' } | { status: 'error'; text: string }
export type Grab = (id: string, target: BranchTarget, directions?: { backward: boolean; forward: boolean }) => Promise<void>

/** One paper's next layer, fetched on a click. State is per paper id so each row keeps its own line. */
export function useGrab(workspaceId: string): { grabs: Record<string, GrabState>; grab: Grab } {
  const snowball = useSnowball(workspaceId)
  const client = useQueryClient()
  const [grabs, setGrabs] = useState<Record<string, GrabState>>({})
  const put = (id: string, state: GrabState) => setGrabs((prev) => ({ ...prev, [id]: state }))
  const grab: Grab = async (id, target, directions = { backward: true, forward: true }) => {
    put(id, { status: 'pending' })
    try {
      const out = await snowball.mutateAsync({
        seed_hit_ids: 'hit_id' in target ? [target.hit_id] : [],
        seed_paper_ids: 'paper_id' in target ? [target.paper_id] : [],
        ...directions,
      })
      const failed = Object.values(out.errors)[0]
      put(id, failed ? { status: 'error', text: friendlySnowballError(failed) } : { status: 'done' })
      await refreshTree(client, workspaceId)
    } catch (e) {
      put(id, { status: 'error', text: friendlySnowballError(e instanceof Error ? e.message : 'Could not fetch the next papers.') })
    }
  }
  return { grabs, grab }
}
