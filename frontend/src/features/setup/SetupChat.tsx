import { Cloud, Download, ExternalLink, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import type { LLMConnection, LLMModel, PullProgressEvent } from '@/api/client'
import { useAvailableModels, useConnectionMutations, useConnections } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { AddModelDialog } from '@/features/settings/AddModelDialog'
import { ConnectionDialog } from '@/features/settings/ConnectionDialog'
import { describePull } from '@/features/settings/pullProgress'
import { usePullModel } from '@/features/settings/usePullModel'
import { isLinux, LINUX_OLLAMA, listedModelId, pullLabel, suggestedPulls } from './setup'
import { StepButtons } from './StepButtons'

/**
 * Step 1 (spec §5): a chat model from Ollama (installed, or pulled here with its live progress) or a cloud connection
 * (M9's dialogs). The model picked or pulled becomes chat's default (PUT /api/llm/default).
 */
export function SetupChat({ onNext }: { onNext: () => void }) {
  const connections = useConnections()
  // The first Ollama connection: the one PaperLab seeds on first start. Its installed models answer "is Ollama there".
  const ollama = connections.data?.find((connection) => connection.kind === 'ollama')
  const installed = useAvailableModels(ollama?.id ?? '', ollama !== undefined)
  const { addModel, setDefault } = useConnectionMutations()
  const [chosen, setChosen] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [cloud, setCloud] = useState<LLMConnection | null>(null)
  const { state: pull, pull: startPull } = usePullModel(ollama?.id ?? '', { onDone: choose })
  const pulling = pull.status === 'pulling'
  const failure = addModel.error ?? setDefault.error

  function choose(model: Pick<LLMModel, 'id' | 'name'>) {
    setDefault.mutate(model.id, { onSuccess: () => setChosen(model.name) })
  }

  function pickInstalled(connection: LLMConnection, name: string) {
    const listed = listedModelId(connection, name)
    if (listed !== null) return choose({ id: listed, name })
    addModel.mutate({ connectionId: connection.id, name }, { onSuccess: choose })
  }

  return (
    <section aria-labelledby="setup-chat-heading" className="flex flex-col gap-4">
      <h2 id="setup-chat-heading" className="font-heading text-xl font-semibold">
        Chat
      </h2>
      <p className="text-sm text-muted-foreground">The model you pick becomes chat's default. Change it any time in Settings.</p>

      {ollama !== undefined && installed.data !== undefined ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm font-medium">Ollama on this computer</p>
          <div className="flex flex-wrap gap-2">
            {(installed.data.models ?? []).map((name) => (
              <Button key={name} variant="outline" size="sm" disabled={pulling} onClick={() => pickInstalled(ollama, name)}>
                Use {name}
              </Button>
            ))}
          </div>
          {suggestedPulls(installed.data.models ?? []).map((suggestion) => (
            <div key={suggestion.name} className="flex flex-wrap items-center gap-3">
              <Button variant="outline" size="sm" disabled={pulling} onClick={() => void startPull(suggestion.name)}>
                <Download aria-hidden />
                {pullLabel(suggestion)}
              </Button>
              <span className="text-xs text-muted-foreground">{suggestion.note}</span>
            </div>
          ))}
          {pull.status === 'pulling' && <PullProgress name={pull.name} line={pull.line} />}
          {pull.status === 'error' && (
            <Alert variant="destructive" className="border-glass-border">
              <AlertDescription>{pull.message}</AlertDescription>
            </Alert>
          )}
        </div>
      ) : (
        <NoOllama
          looking={connections.isPending || installed.isFetching}
          retry={() => void (ollama === undefined ? connections.refetch() : installed.refetch())}
        />
      )}

      <div>
        <Button variant="outline" onClick={() => setAdding(true)}>
          <Cloud aria-hidden />
          Use a cloud model
        </Button>
      </div>

      {chosen !== null && (
        <p role="status" className="setup-chat-choice text-sm">
          Chat uses {chosen}.
        </p>
      )}
      {failure && (
        <Alert variant="destructive" className="border-glass-border">
          <AlertDescription>{failure.message}</AlertDescription>
        </Alert>
      )}

      <StepButtons next="Continue" busy={pulling} onNext={onNext} />

      <ConnectionDialog open={adding} onOpenChange={setAdding} onCreated={setCloud} />
      {cloud !== null && (
        <AddModelDialog
          connection={cloud}
          open
          onOpenChange={(open) => {
            if (!open) setCloud(null)
          }}
          onAdded={choose}
        />
      )}
    </section>
  )
}

function PullProgress({ name, line }: { name: string; line: PullProgressEvent | null }) {
  const progress = line ? describePull({ status: line.status, total: line.total ?? null, completed: line.completed ?? null }) : null
  return (
    <div className="flex flex-col gap-1">
      <Progress aria-label={`Pulling ${name}`} value={progress?.percent ?? null} />
      <p className="text-xs tabular-nums text-muted-foreground">{progress?.label ?? 'Starting…'}</p>
    </div>
  )
}

function NoOllama({ looking, retry }: { looking: boolean; retry: () => void }) {
  if (looking) return <p className="text-sm text-muted-foreground">Looking for Ollama…</p>
  return (
    <div className="flex flex-col gap-2 text-sm">
      <p>Ollama isn't running on this computer. With it, chat stays on this computer: install it, then press Retry.</p>
      {isLinux(navigator.userAgent) && <p className="text-muted-foreground">{LINUX_OLLAMA}</p>}
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" asChild>
          <a href="https://ollama.com" target="_blank" rel="noreferrer">
            <ExternalLink aria-hidden />
            Get Ollama
          </a>
        </Button>
        <Button variant="outline" size="sm" onClick={retry}>
          <RefreshCw aria-hidden />
          Retry
        </Button>
      </div>
    </div>
  )
}
