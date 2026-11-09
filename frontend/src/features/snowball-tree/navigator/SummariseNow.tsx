import { useState } from 'react'
import { ApiError, isConflict } from '@/api/client'
import { useSuggestHit } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { RemoteConfirmDialog } from '@/features/manuscripts/review/RemoteConfirm'

const MESSAGES: Record<string, string> = {
  needs_criteria: 'Set your review question in Search & screen first.',
  prescreen_running: 'The AI is pre-screening this workspace; try again when it finishes.',
  suggest_timeout: 'The AI took too long; try again.',
  model_unavailable: 'The AI model is not available right now.',
}
const failure = (e: unknown) => (e instanceof ApiError && MESSAGES[e.code]) || (e instanceof Error ? e.message : 'Could not summarise this paper.')

/** "Summarise now" for one hit: the AI reads it against the review question. Old suggestion stays if it fails. */
export function SummariseNow({ workspaceId, hitId }: { workspaceId: string; hitId: string }) {
  const suggest = useSuggestHit(workspaceId)
  const [error, setError] = useState<string | null>(null)
  const [host, setHost] = useState<string | null>(null)
  const run = async (confirmRemote: boolean) => {
    setError(null)
    setHost(null)
    try {
      await suggest.mutateAsync({ hitId, confirmRemote })
    } catch (e) {
      if (isConflict(e, 'remote_model_needs_confirm')) setHost(String((e as ApiError).body.host ?? 'a remote model'))
      else setError(failure(e))
    }
  }
  return (
    <>
      <Button type="button" size="xs" variant="outline" disabled={suggest.isPending} onClick={() => run(false)}>
        {suggest.isPending ? 'Reading…' : 'Summarise now'}
      </Button>
      {error && <span role="alert" className="block text-xs text-destructive">{error}</span>}
      <RemoteConfirmDialog what="text" host={host} onSend={() => run(true)} onCancel={() => setHost(null)} />
    </>
  )
}
