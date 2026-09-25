import { Cloud, Plus } from 'lucide-react'
import { useState } from 'react'
import type { EmbeddingStatus, LLMConnection } from '@/api/client'
import { useAvailableModels, useConnections } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ConnectionDialog } from './ConnectionDialog'
import { DownloadSearchModel } from './DownloadSearchModel'
import {
  defaultModel,
  eligibleConnections,
  noConnection,
  OPENAI_MODELS,
  picksOf,
  samePicks,
  SOURCE_KINDS,
  SOURCE_NAMES,
  sourceLabel,
  whereLine,
  type SourceKind,
  type SourcePick,
} from './searchSources'
import { SwitchSourceDialog } from './SwitchSourceDialog'

/** M9's Cloud tag: an icon and a word, never colour alone. */
export function CloudTag() {
  return (
    <Badge variant="outline" className="cloud-tag gap-1">
      <Cloud aria-hidden />
      Cloud
    </Badge>
  )
}

/**
 * Settings → Search's picker (D131, §5): the kind, its connection and its model, then "Switch search to <label>" once
 * they differ from the source in use. EmbeddingSettings keys it by the source in use, so it starts over after a switch.
 */
export function SearchSourcePicker({ status }: { status: EmbeddingStatus }) {
  const connections = useConnections()
  const [picks, setPicks] = useState<SourcePick>(() => picksOf(status.source))
  const [adding, setAdding] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const eligible = eligibleConnections(picks.kind, connections.data ?? [])
  // A new kind, or a connection just added, starts on the first eligible connection.
  const connection = eligible.find((c) => c.id === picks.connectionId) ?? eligible[0]
  const chosen: SourcePick = { ...picks, connectionId: picks.kind === 'builtin' ? null : (connection?.id ?? null) }
  const label = sourceLabel(chosen.kind, connection)
  const where = whereLine(chosen.kind, connection)
  const missing = noConnection(chosen.kind)
  const blocked =
    (chosen.kind === 'builtin' && !status.model_present) ||
    (chosen.kind !== 'builtin' && chosen.connectionId === null) ||
    (chosen.kind === 'openai_compatible' && chosen.model.trim() === '')

  function closeDialog(open: boolean) {
    setConfirming(open)
    if (!open) setPicks(picksOf(status.source)) // Cancel sends nothing and goes back to the source in use
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-1.5">
        <Label htmlFor="search-source">Search source</Label>
        <Select value={chosen.kind} onValueChange={(kind) => setPicks({ kind: kind as SourceKind, connectionId: null, model: defaultModel(kind as SourceKind) })}>
          <SelectTrigger id="search-source" aria-label="Search source" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SOURCE_KINDS.map((kind) => (
              <SelectItem key={kind} value={kind}>
                {SOURCE_NAMES[kind]}
                {(kind === 'openai' || kind === 'gemini') && <CloudTag />}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {where && <p className="text-xs text-muted-foreground">{where}</p>}
      </div>

      {missing && connection === undefined && (
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span>{missing.line}</span>
          <Button variant="outline" size="sm" onClick={() => setAdding(true)}>
            <Plus aria-hidden />
            {missing.button}
          </Button>
        </div>
      )}
      {connection !== undefined && (
        <ConnectionField eligible={eligible} value={connection.id} onPick={(id) => setPicks({ ...chosen, connectionId: id })} />
      )}
      {chosen.kind !== 'builtin' && <ModelField picks={chosen} onModel={(model) => setPicks({ ...chosen, model })} />}
      {/* Picking Built-in never downloads by itself (D133): the block shows its status and the Download button. */}
      {chosen.kind === 'builtin' && <DownloadSearchModel alwaysShowStatus />}

      {!samePicks(chosen, picksOf(status.source)) && (
        <div>
          <Button disabled={blocked} onClick={() => setConfirming(true)}>
            Switch search to {label}
          </Button>
        </div>
      )}

      <SwitchSourceDialog
        open={confirming}
        onOpenChange={closeDialog}
        picks={chosen}
        target={{ kind: chosen.kind, label, model: chosen.model, isLocal: chosen.kind === 'builtin' || connection?.is_local === true }}
        library={status}
      />
      <ConnectionDialog open={adding} onOpenChange={setAdding} preset={missing?.preset} />
    </div>
  )
}

type ConnectionFieldProps = { eligible: LLMConnection[]; value: string; onPick: (id: string) => void }

function ConnectionField({ eligible, value, onPick }: ConnectionFieldProps) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor="search-connection">Connection</Label>
      <Select value={value} onValueChange={onPick}>
        <SelectTrigger id="search-connection" aria-label="Connection" className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {eligible.map((c) => (
            <SelectItem key={c.id} value={c.id}>
              {c.label}
              {!c.is_local && <CloudTag />}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

/** OpenAI: a Select of its two models. Gemini and Ollama: their one model. A compatible server: typed, with the
 * server's own list as native suggestions when it has one (any other name still works). */
function ModelField({ picks, onModel }: { picks: SourcePick; onModel: (model: string) => void }) {
  const compatible = picks.kind === 'openai_compatible'
  const listed = useAvailableModels(picks.connectionId ?? '', compatible && picks.connectionId !== null)
  if (picks.kind === 'ollama' || picks.kind === 'gemini') {
    return (
      <p className="text-sm">
        <span className="text-muted-foreground">Model </span>
        <span className="font-mono">{picks.model}</span>
      </p>
    )
  }
  return (
    <div className="grid gap-1.5">
      <Label htmlFor="search-model">Model</Label>
      {compatible ? (
        <>
          <Input
            id="search-model"
            list="search-models"
            placeholder="Model name, for example nomic-embed-text-v1.5"
            value={picks.model}
            onChange={(e) => onModel(e.target.value)}
          />
          <datalist id="search-models">
            {(listed.data?.models ?? []).map((model) => (
              <option key={model} value={model} />
            ))}
          </datalist>
        </>
      ) : (
        <Select value={picks.model} onValueChange={onModel}>
          <SelectTrigger id="search-model" aria-label="Model" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {OPENAI_MODELS.map((model) => (
              <SelectItem key={model} value={model}>
                {model}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </div>
  )
}
