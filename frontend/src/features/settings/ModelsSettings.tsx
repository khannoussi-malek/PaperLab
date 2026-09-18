import { Plus } from 'lucide-react'
import { useState } from 'react'
import { useConnections } from '@/api/queries'
import { delayedIn } from '@/components/motion'
import { Alert, AlertAction, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { ConnectionCard } from './ConnectionCard'
import { ConnectionDialog } from './ConnectionDialog'

/** The "Model connections" section: add, test, edit and delete connections, and pick which models chat lists. */
export function ModelsSettings() {
  const connections = useConnections()
  const [addOpen, setAddOpen] = useState(false)
  const list = connections.data

  return (
    <section aria-labelledby="model-connections-heading" className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <h2 id="model-connections-heading" className="font-heading text-xl font-semibold">
          Model connections
        </h2>
        <Button onClick={() => setAddOpen(true)}>
          <Plus aria-hidden />
          Add connection
        </Button>
      </div>

      {list === undefined ? (
        connections.isError ? (
          <Alert variant="destructive" className="border-glass-border">
            <AlertDescription>{connections.error.message}</AlertDescription>
            <AlertAction>
              <Button variant="outline" size="xs" onClick={() => void connections.refetch()}>
                Retry
              </Button>
            </AlertAction>
          </Alert>
        ) : (
          <p className={cn('text-muted-foreground', delayedIn)}>Loading…</p>
        )
      ) : list.length === 0 ? (
        <div className="rounded-xl border border-dashed border-glass-border px-6 py-10 text-center text-muted-foreground">
          No model connections yet. Add Ollama, Anthropic or any OpenAI-compatible server.
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {list.map((connection) => (
            <ConnectionCard key={connection.id} connection={connection} />
          ))}
        </div>
      )}

      <ConnectionDialog open={addOpen} onOpenChange={setAddOpen} />
    </section>
  )
}
