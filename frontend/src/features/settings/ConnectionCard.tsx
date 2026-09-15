import { Cloud, CircleAlert, CircleCheck, HardDrive, Info, Pencil, PlugZap, Plus, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import type { LLMConnection } from '@/api/client'
import { useConnectionMutations } from '@/api/queries'
import { glass } from '@/components/glass'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { cn } from '@/lib/utils'
import { AddModelDialog } from './AddModelDialog'
import { hostOf, KIND_NAMES, type ConnectionKind } from './connectionForm'
import { ConnectionDialog } from './ConnectionDialog'

/** "•••• T123", "••••" for a key too short to hint, or "No key". */
function keyHintText(connection: LLMConnection): string {
  if (!connection.has_key) return 'No key'
  return connection.key_hint ? `•••• ${connection.key_hint}` : '••••'
}

export function ConnectionCard({ connection }: { connection: LLMConnection }) {
  const { test, remove, removeModel, setDefault } = useConnectionMutations()
  const [editOpen, setEditOpen] = useState(false)
  const [addModelOpen, setAddModelOpen] = useState(false)
  const host = hostOf(connection.kind, connection.base_url)
  const defaultModel = connection.models.find((model) => model.is_default)
  const radioLabelId = `default-model-${connection.id}`

  function deleteConnection() {
    const question = `Delete "${connection.label}" and its models? Saved answers keep their model names.`
    if (window.confirm(question)) remove.mutate(connection.id)
  }

  return (
    <article
      className={cn(glass, 'connection-card group ring-1 ring-glass-border rounded-xl p-4 flex flex-col gap-3')}
      data-connection-id={connection.id}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate font-heading text-lg font-semibold" title={connection.label}>
            {connection.label}
          </h3>
          <p className="text-sm text-muted-foreground">
            {KIND_NAMES[connection.kind as ConnectionKind] ?? connection.kind} · {host}
          </p>
          <div className="mt-1.5 flex items-center gap-2">
            <Badge variant="outline" className="cloud-tag gap-1">
              {connection.is_local ? (
                <>
                  <HardDrive aria-hidden />
                  Local
                </>
              ) : (
                <>
                  <Cloud aria-hidden />
                  Cloud
                </>
              )}
            </Badge>
            {connection.kind !== 'ollama' && (
              <span className="key-hint font-mono text-xs tabular-nums text-muted-foreground">{keyHintText(connection)}</span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Button variant="outline" size="sm" onClick={() => test.mutate(connection.id)} disabled={test.isPending}>
            <PlugZap aria-hidden />
            {test.isPending ? 'Testing…' : 'Test'}
          </Button>
          <Button variant="ghost" size="icon-sm" aria-label="Edit connection" onClick={() => setEditOpen(true)}>
            <Pencil aria-hidden />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Delete connection"
            className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
            onClick={deleteConnection}
          >
            <Trash2 aria-hidden />
          </Button>
        </div>
      </div>

      {test.data && (
        <p role="status" className={cn('test-result flex items-center gap-1.5 text-sm', !test.data.ok && 'text-destructive')}>
          {test.data.ok ? <CircleCheck aria-hidden className="size-4 shrink-0" /> : <CircleAlert aria-hidden className="size-4 shrink-0" />}
          {test.data.message}
        </p>
      )}

      {!connection.is_local && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Info aria-hidden className="size-3.5 shrink-0" />
          Passages and notes from your library are sent to {host}
        </p>
      )}

      <div className="border-t border-glass-border pt-3">
        <div className="flex items-center justify-between gap-2">
          {connection.models.length > 0 && (
            <Label id={radioLabelId} className="text-sm font-medium">
              Default model
            </Label>
          )}
          <Button variant="ghost" size="xs" className="ml-auto" onClick={() => setAddModelOpen(true)}>
            <Plus aria-hidden />
            Add model
          </Button>
        </div>

        {connection.models.length === 0 ? (
          <p className="mt-1 text-sm text-muted-foreground">No models in chat yet.</p>
        ) : (
          <RadioGroup
            aria-labelledby={radioLabelId}
            value={defaultModel?.id ?? ''}
            onValueChange={(id) => setDefault.mutate(id)}
            className="mt-2 gap-1"
          >
            {connection.models.map((model) => (
              <li
                key={model.id}
                className="model-row group/row flex items-center gap-2 rounded-md px-1 py-1"
                data-model-id={model.id}
              >
                <RadioGroupItem value={model.id} aria-label={model.name} />
                <span className="min-w-0 flex-1 truncate font-mono text-sm" title={model.name}>
                  {model.name}
                </span>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-label={`Remove ${model.name} from chat`}
                  className="text-muted-foreground group-hover/row:text-destructive group-focus-within/row:text-destructive hover:bg-destructive/10"
                  onClick={() => removeModel.mutate(model.id)}
                >
                  <X aria-hidden />
                </Button>
              </li>
            ))}
          </RadioGroup>
        )}
      </div>

      <ConnectionDialog open={editOpen} onOpenChange={setEditOpen} connection={connection} />
      <AddModelDialog connection={connection} open={addModelOpen} onOpenChange={setAddModelOpen} />
    </article>
  )
}
