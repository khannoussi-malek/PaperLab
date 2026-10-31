import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { api, type Diagram } from '@/api/client'
import { isLive } from './diagramModel'

const POLL_MS = 2000

/** One diagram draft in the dialog; polls every 2 s only while it is queued or running. Nothing here touches a file. */
export function useDiagram(manuscriptId: string) {
  const qc = useQueryClient()
  const [id, setId] = useState<string | null>(null)
  const confirmed = useRef(false)
  // Bumped by discard: a create that resolves after the dialog closed deletes its draft instead of showing it.
  const epoch = useRef(0)
  const keyOf = (did: string | null) => ['manuscriptDiagram', manuscriptId, did]
  const query = useQuery({
    queryKey: keyOf(id),
    queryFn: () => api.diagram(manuscriptId, id!),
    enabled: id !== null,
    // A failing poll stops (as useReview does); the dialog says the run was lost instead of spinning.
    refetchInterval: (q) => (q.state.status !== 'error' && q.state.data && isLive(q.state.data) ? POLL_MS : false),
  })

  /** A response the server just gave wins over a poll still in flight (which would bring back the older state). */
  const show = async (row: Diagram) => {
    await qc.cancelQueries({ queryKey: keyOf(row.id) })
    qc.setQueryData(keyOf(row.id), row)
    setId(row.id)
    return row
  }
  const remove = async (did: string) => {
    qc.removeQueries({ queryKey: keyOf(did) })
    try {
      await api.deleteDiagram(manuscriptId, did)
    } catch (e) {
      console.error('could not delete diagram draft', did, e) // ponytail: the server prunes old drafts anyway
    }
  }
  /** A new run; a draft already shown is dropped once the new one exists. */
  const create = async (description: string, confirmRemote: boolean) => {
    const old = id
    const at = epoch.current
    const row = await api.createDiagram(manuscriptId, { description: description.trim(), confirm_remote: confirmRemote })
    if (epoch.current !== at) { // closed meanwhile: don't leave a remote generation running unseen
      await remove(row.id)
      return row
    }
    confirmed.current = confirmRemote
    await show(row)
    if (old !== null && old !== row.id) await remove(old)
    return row
  }
  const diagram = id === null ? null : (query.data ?? null)

  return {
    diagram,
    /** Polling this draft failed: its state is unknown. */
    lost: id !== null && query.isError,
    create,
    /** The researcher's edit: re-checked and recompiled by the server; polling resumes. */
    editCode: async (code: string) => id && show(await api.setDiagramCode(manuscriptId, id, code)),
    cancel: async () => id && show(await api.cancelDiagram(manuscriptId, id)),
    /** A new run from the same description; the old draft is dropped. */
    regenerate: async () => diagram && create(diagram.description, confirmed.current),
    /** Drops the draft (closing without Insert). */
    discard: async () => {
      epoch.current += 1
      if (id === null) return
      setId(null)
      await remove(id)
    },
  }
}
