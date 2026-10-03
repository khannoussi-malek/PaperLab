import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { keys, useSaveCriteria, useScreeningState, useStartSuggestions, useStopSuggestions } from '@/api/queries'
import { Button } from '@/components/ui/button'

const CRITERIA_MAX = 4000

/** Workspace criteria and the on-request suggestion job (M31b, D188, D189). Never starts by itself. */
export function ScreeningAssist({ workspaceId }: { workspaceId: string }) {
  const state = useScreeningState(workspaceId)
  const save = useSaveCriteria(workspaceId)
  const start = useStartSuggestions(workspaceId)
  const stop = useStopSuggestions(workspaceId)
  const client = useQueryClient()
  const [draft, setDraft] = useState<string | null>(null)
  const status = state.data?.suggest_status
  const previous = useRef(status)
  useEffect(() => {
    if (previous.current && previous.current !== 'idle' && status === 'idle') {
      client.invalidateQueries({ queryKey: keys.searchHitsRoot(workspaceId) })
      client.invalidateQueries({ queryKey: keys.rankedHits(workspaceId) })
    }
    previous.current = status
  }, [status, client, workspaceId])

  if (!state.data) return null
  const data = state.data
  const criteria = draft ?? data.criteria ?? ''
  const running = status !== 'idle'
  const noModel = data.model_label === null

  function onSuggest() {
    const remote = data.model_is_local === false
    if (remote && !window.confirm(`Abstracts will be sent to ${data.model_host} and may cost money. Continue?`)) return
    start.mutate(remote)
  }

  return (
    <div className="flex flex-col gap-2 border-b px-3 py-2 text-sm">
      <label className="flex flex-col gap-1">
        <span>Inclusion / exclusion criteria</span>
        <textarea
          value={criteria}
          maxLength={CRITERIA_MAX}
          disabled={running}
          onChange={(event) => setDraft(event.target.value)}
          rows={3}
          className="rounded-lg border bg-background px-2 py-1"
        />
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={running || draft === null || save.isPending}
          onClick={() => save.mutate(criteria, { onSuccess: () => setDraft(null) })}
        >
          Save criteria
        </Button>
        {running ? (
          <>
            <span className="text-muted-foreground">
              Suggesting… {data.suggest_done} / {data.suggest_total}
            </span>
            <Button type="button" size="sm" variant="outline" disabled={status === 'stopping'} onClick={() => stop.mutate()}>
              Stop
            </Button>
          </>
        ) : (
          <Button type="button" size="sm" disabled={noModel || !data.criteria || start.isPending} onClick={onSuggest}>
            Suggest for unscreened hits
          </Button>
        )}
        {noModel && <span className="text-xs text-muted-foreground">Set up a chat model in Settings to get suggestions.</span>}
      </div>
      {(data.suggest_error || start.error || save.error) && (
        <p role="alert" className="text-xs text-destructive">
          {data.suggest_error ?? start.error?.message ?? save.error?.message}
        </p>
      )}
    </div>
  )
}
