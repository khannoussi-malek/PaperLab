import { useState, type FormEvent } from 'react'
import type { LLMConnection } from '@/api/client'
import { useConnectionMutations } from '@/api/queries'
import { glass } from '@/components/glass'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { createBody, hostOf, KIND_NAMES, updateBody, type ConnectionForm, type ConnectionKind } from './connectionForm'
import { applyPreset, OLLAMA_BASE_URL, PRESETS } from './presets'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Omitted: "Add connection". Set: "Edit connection", starting from its saved values. */
  connection?: LLMConnection
  /** Called with the connection this dialog just created (the first-run setup then asks for its model). */
  onCreated?: (connection: LLMConnection) => void
}

function initialForm(connection?: LLMConnection): ConnectionForm {
  if (!connection) return { kind: 'openai_compatible', label: '', baseUrl: '', apiKey: '', keyChange: 'replace' }
  return {
    kind: connection.kind as ConnectionKind,
    label: connection.label,
    baseUrl: connection.base_url ?? '',
    apiKey: '',
    keyChange: 'keep',
  }
}

type KeyFieldProps = {
  form: ConnectionForm
  set: (patch: Partial<ConnectionForm>) => void
  connection?: LLMConnection
  showNotice: boolean
}

/** The stored key as "•••• T123" with Replace/Remove, or (once replacing, or for a new connection) the input itself. */
function KeyField({ form, set, connection, showNotice }: KeyFieldProps) {
  const showStoredKey = connection !== undefined && connection.has_key && form.keyChange !== 'replace'
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={showStoredKey ? undefined : 'connection-api-key'}>API key</Label>
      {showStoredKey ? (
        <div className="flex items-center justify-between gap-2 rounded-lg border border-input px-2.5 py-1.5">
          <span className="font-mono text-sm tabular-nums text-muted-foreground">
            {form.keyChange === 'remove' ? 'The key will be removed' : `•••• ${connection?.key_hint ?? ''}`}
          </span>
          <div className="flex shrink-0 gap-1">
            <Button type="button" variant="outline" size="xs" onClick={() => set({ keyChange: 'replace' })}>
              Replace key
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="xs"
              className="text-destructive hover:bg-destructive/10 hover:text-destructive"
              onClick={() => set({ keyChange: 'remove' })}
            >
              Remove key
            </Button>
          </div>
        </div>
      ) : (
        <Input
          id="connection-api-key"
          type="password"
          autoComplete="off"
          value={form.apiKey}
          onChange={(e) => set({ apiKey: e.target.value, keyChange: 'replace' })}
        />
      )}
      {showNotice && <p className="text-xs text-muted-foreground">Changing the address removes the saved key.</p>}
    </div>
  )
}

/** Add or edit an Ollama, Anthropic or OpenAI-compatible connection. Never calls the provider: Test connection does that. */
export function ConnectionDialog({ open, onOpenChange, connection, onCreated }: Props) {
  const { create, update } = useConnectionMutations()
  const [form, setForm] = useState<ConnectionForm>(() => initialForm(connection))
  const [preset, setPreset] = useState('Custom')
  const set = (patch: Partial<ConnectionForm>) => setForm((current) => ({ ...current, ...patch }))

  function openChange(next: boolean) {
    if (next) {
      setForm(initialForm(connection))
      setPreset('Custom')
    } else {
      // A typed key is never left sitting in the field, nor in the mutation's own `variables`.
      set({ apiKey: '' })
      create.reset()
      update.reset()
    }
    onOpenChange(next)
  }

  function setKind(kind: ConnectionKind) {
    set({ kind, baseUrl: kind === 'ollama' && form.baseUrl.trim() === '' ? OLLAMA_BASE_URL : form.baseUrl })
  }

  function pickPreset(name: string) {
    setPreset(name)
    set(applyPreset(name, { label: form.label, baseUrl: form.baseUrl }))
  }

  const keyWillBeSent = form.keyChange === 'replace' && form.apiKey.trim() !== ''
  const hostChanged =
    connection !== undefined &&
    connection.has_key &&
    form.kind === 'openai_compatible' &&
    form.baseUrl.trim() !== '' &&
    hostOf(form.kind, form.baseUrl) !== hostOf(connection.kind, connection.base_url)
  const showKeyDropNotice = hostChanged && !keyWillBeSent

  async function submit(event: FormEvent) {
    event.preventDefault()
    try {
      if (connection) {
        await update.mutateAsync({ id: connection.id, ...updateBody(form) })
      } else {
        onCreated?.(await create.mutateAsync(createBody(form)))
      }
      openChange(false)
    } catch {
      // shown below, from create.error / update.error
    }
  }

  const pending = connection ? update.isPending : create.isPending
  const error = (connection ? update.error : create.error)?.message
  const canSave = form.label.trim() !== '' && (form.kind === 'anthropic' || form.baseUrl.trim() !== '')

  return (
    <Dialog open={open} onOpenChange={openChange}>
      <DialogContent className={cn(glass, 'bg-glass-strong ring-glass-border sm:max-w-md')}>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{connection ? 'Edit connection' : 'Add connection'}</DialogTitle>
          </DialogHeader>

          <div className="grid gap-1.5">
            <Label htmlFor="connection-kind">Kind</Label>
            <Select value={form.kind} onValueChange={(value) => setKind(value as ConnectionKind)} disabled={connection !== undefined}>
              <SelectTrigger id="connection-kind" aria-label="Kind" disabled={connection !== undefined} className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(KIND_NAMES) as ConnectionKind[]).map((kind) => (
                  <SelectItem key={kind} value={kind}>
                    {KIND_NAMES[kind]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {form.kind === 'openai_compatible' && (
            <div className="grid gap-1.5">
              <Label htmlFor="connection-preset">Preset</Label>
              <Select value={preset} onValueChange={pickPreset}>
                <SelectTrigger id="connection-preset" aria-label="Preset" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PRESETS.map((p) => (
                    <SelectItem key={p.name} value={p.name}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="grid gap-1.5">
            <Label htmlFor="connection-name">Name</Label>
            <Input id="connection-name" required value={form.label} onChange={(e) => set({ label: e.target.value })} />
          </div>

          {form.kind !== 'anthropic' && (
            <div className="grid gap-1.5">
              <Label htmlFor="connection-base-url">Base URL</Label>
              <Input
                id="connection-base-url"
                type="url"
                required
                value={form.baseUrl}
                onChange={(e) => set({ baseUrl: e.target.value })}
              />
            </div>
          )}

          {form.kind !== 'ollama' && <KeyField form={form} set={set} connection={connection} showNotice={showKeyDropNotice} />}

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={pending || !canSave}>
              {pending ? 'Saving…' : 'Save connection'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
