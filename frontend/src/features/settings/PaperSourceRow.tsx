import { CircleDollarSign, Info } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import type { PaperSource } from '@/api/client'
import { useUpdatePaperSources } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { DESCRIPTIONS, keyLine, OPENALEX_PRICE } from './paperSources'

type Props = { source: PaperSource; hasEmail: boolean }

/** One source: its switch (saved on change), what it is for, and for keyed sources the API key. */
export function PaperSourceRow({ source, hasEmail }: Props) {
  // Each row owns its save, so a refusal shows under the source it belongs to.
  const update = useUpdatePaperSources()
  const [key, setKey] = useState('')
  const switchId = `paper-source-${source.id}`
  const keyId = `paper-source-${source.id}-key`

  async function saveKey(event: FormEvent) {
    event.preventDefault()
    try {
      await update.mutateAsync({ api_keys: { [source.id]: key.trim() } })
      // A typed key is never left sitting in the field, nor in the mutation's own `variables`.
      setKey('')
      update.reset()
    } catch {
      // shown below, from update.error
    }
  }

  function removeKey() {
    if (window.confirm(`Remove the ${source.name} API key? You would have to paste it again to use it.`)) {
      update.mutate({ api_keys: { [source.id]: null } })
    }
  }

  return (
    <li className="paper-source-row flex flex-col gap-1.5 px-4 py-3" data-source-id={source.id}>
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
        <Checkbox
          id={switchId}
          checked={source.enabled}
          disabled={update.isPending}
          onCheckedChange={(checked) => update.mutate({ enabled: { [source.id]: checked === true } })}
        />
        <Label htmlFor={switchId} className="font-heading text-base font-semibold">
          {source.name}
        </Label>
        {source.id === 'openalex' && (
          <Badge variant="outline">
            <CircleDollarSign aria-hidden />
            May cost money
          </Badge>
        )}
      </div>
      {/* Indented under the name: the checkbox (size-4) plus the row's gap. */}
      <div className="flex flex-col gap-1.5 pl-6.5">
        <p className="text-sm text-muted-foreground">{DESCRIPTIONS[source.id]}</p>
        {source.id === 'openalex' && <p className="text-xs text-muted-foreground">{OPENALEX_PRICE}</p>}
        {source.id === 'unpaywall' && !hasEmail && (
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Info aria-hidden className="size-3.5 shrink-0" />
            Add a contact email to use Unpaywall.
          </p>
        )}

        {/* has_key is null for a source that takes no key. */}
        {source.has_key === true && (
          <div className="flex items-center gap-2">
            <span className="key-hint text-sm tabular-nums text-muted-foreground">{keyLine(source.key_hint)}</span>
            <Button
              variant="ghost"
              size="xs"
              className="text-destructive hover:bg-destructive/10 hover:text-destructive"
              disabled={update.isPending}
              onClick={removeKey}
            >
              Remove key
            </Button>
          </div>
        )}
        {source.has_key === false && (
          <form className="mt-1 grid gap-1.5" onSubmit={saveKey}>
            <Label htmlFor={keyId}>
              {/* The visible label is the spec's "API key"; the name says whose, as three rows have one. */}
              <span className="sr-only">{source.name} </span>API key
            </Label>
            <div className="flex gap-2">
              <Input
                id={keyId}
                type="password"
                autoComplete="off"
                placeholder="Optional"
                className="max-w-xs"
                value={key}
                onChange={(event) => setKey(event.target.value)}
              />
              <Button type="submit" variant="outline" disabled={update.isPending || key.trim() === ''}>
                Save key
              </Button>
            </div>
          </form>
        )}

        {update.error && (
          <Alert variant="destructive" className="border-glass-border">
            <AlertDescription>{update.error.message}</AlertDescription>
          </Alert>
        )}
      </div>
    </li>
  )
}
