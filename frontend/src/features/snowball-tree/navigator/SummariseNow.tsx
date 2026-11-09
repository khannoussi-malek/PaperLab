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
  no_model: 'No AI model is set up. Add one in Settings → AI.',
}
const UNREAD: Record<string, string> = { no_abstract: 'No abstract to read yet.', model_error: 'The AI could not read this paper.' }
const failure = (e: unknown) => (e instanceof ApiError && MESSAGES[e.code]) || (e instanceof Error ? e.message : 'Could not summarise this paper.')

/** "Summarise now" for one hit: the AI reads it against the review question. Old suggestion stays if it fails. */
export function SummariseNow({ workspaceId, hitId, describedBy }: { workspaceId: string; hitId: string; describedBy?: string }) {
  const suggest = useSuggestHit(workspaceId)
  const [error, setError] = useState<string | null>(null)
  const [host, setHost] = useState<string | null>(null)
  const run = async (confirmRemote: boolean) => {
    setError(null)
    setHost(null)
    try {
      const out = await suggest.mutateAsync({ hitId, confirmRemote })
      const flag = (out.suggestion_flags ?? []).find((f) => f in UNREAD)
      if (flag) setError(UNREAD[flag])
    } catch (e) {
      if (isConflict(e, 'remote_model_needs_confirm')) setHost(String((e as ApiError).body.host ?? 'a remote model'))
      else setError(failure(e))
    }
  }
  return (
    <>
      <Button type="button" size="xs" variant="outline" aria-describedby={describedBy} disabled={suggest.isPending} onClick={() => run(false)}>
        {suggest.isPending ? 'Reading…' : 'Summarise now'}
      </Button>
      {error && <span role="alert" className="text-xs text-destructive">{error}</span>}
      <RemoteConfirmDialog what="text" host={host} onSend={() => run(true)} onCancel={() => { setHost(null); setError('Not summarised.') }} />
    </>
  )
}
