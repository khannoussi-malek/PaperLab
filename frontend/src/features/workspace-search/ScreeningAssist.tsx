import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { keys, useSaveCriteria, useScreeningState, useStartSuggestions, useStopSuggestions } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Textarea } from '@/components/ui/textarea'

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
  const percent = data.suggest_total > 0 ? Math.round((data.suggest_done / data.suggest_total) * 100) : null

  function onSuggest() {
    const remote = data.model_is_local === false
    if (remote && !window.confirm(`Abstracts will be sent to ${data.model_host} and may cost money. Continue?`)) return
    start.mutate(remote)
  }

  return (
    <div className="flex flex-col gap-2 border-b px-3 py-2 text-sm">
      <div className="flex flex-col gap-1">
        <Label htmlFor="screening-criteria">Inclusion / exclusion criteria</Label>
        <Textarea
          id="screening-criteria"
          value={criteria}
          maxLength={CRITERIA_MAX}
          disabled={running}
          onChange={(event) => setDraft(event.target.value)}
          rows={3}
        />
      </div>
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
        {!running && (
          <Button type="button" size="sm" disabled={noModel || !data.criteria || start.isPending} onClick={onSuggest}>
            Suggest for unscreened hits
          </Button>
        )}
        {noModel && (
          <span className="text-xs text-muted-foreground">Set up a chat model in Settings to get suggestions.</span>
        )}
      </div>
      {running && (
        <div className="flex flex-col gap-1.5">
          <Progress aria-label="Suggesting" value={percent} />
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs tabular-nums text-muted-foreground">
              Suggesting… {data.suggest_done} / {data.suggest_total}
            </p>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={status === 'stopping'}
              onClick={() => stop.mutate()}
            >
              Stop
            </Button>
          </div>
        </div>
      )}
      {(data.suggest_error || start.error || save.error) && (
        <Alert variant="destructive" className="border-glass-border">
          <AlertDescription>{data.suggest_error ?? start.error?.message ?? save.error?.message}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}
