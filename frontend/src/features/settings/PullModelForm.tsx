import { Download } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import type { LLMConnection, PullProgressEvent } from '@/api/client'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'
import { describePull, type PullLine } from './pullProgress'
import { usePullModel } from './usePullModel'

/** The API sends `total`/`completed` as optional; `describePull` wants them explicitly nullable. */
const asPullLine = (line: PullProgressEvent): PullLine => ({ status: line.status, total: line.total ?? null, completed: line.completed ?? null })

/** An Ollama card's inline pull form: type a name, watch its download live, and land in the model list. */
export function PullModelForm({ connection }: { connection: LLMConnection }) {
  const { state, pull } = usePullModel(connection.id)
  const [name, setName] = useState('')
  const pulling = state.status === 'pulling'

  function submit(event: FormEvent) {
    event.preventDefault()
    const trimmed = name.trim()
    if (trimmed === '') return
    setName('')
    void pull(trimmed)
  }

  return (
    <div className="mt-3 flex flex-col gap-2 border-t border-glass-border pt-3">
      <form onSubmit={submit} className="flex items-center gap-2">
        <Input
          aria-label="Model to pull"
          placeholder="qwen3:8b"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={pulling}
        />
        <Button type="submit" variant="outline" disabled={pulling || name.trim() === ''}>
          <Download aria-hidden />
          Pull
        </Button>
      </form>

      {pulling && (
        <div className="flex flex-col gap-1">
          <Progress aria-label={`Pulling ${state.name}`} value={state.line ? describePull(asPullLine(state.line)).percent : null} />
          <p className="text-xs tabular-nums text-muted-foreground">
            {state.line ? describePull(asPullLine(state.line)).label : 'Starting…'}
          </p>
        </div>
      )}

      {state.status === 'done' && <p className="text-xs text-muted-foreground">Added {state.name} to chat</p>}

      {state.status === 'error' && (
        <Alert variant="destructive" className="border-glass-border">
          <AlertDescription>{state.message}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}
