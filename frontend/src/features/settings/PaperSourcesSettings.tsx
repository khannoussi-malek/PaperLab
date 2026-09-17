import { useState, type FormEvent } from 'react'
import { usePaperSources, useUpdatePaperSources } from '@/api/queries'
import { glass } from '@/components/glass'
import { Alert, AlertAction, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { PaperSourceRow } from './PaperSourceRow'
import { emailProblem } from './paperSources'

/** The contact email: Save (checked here first, in the server's words) and Remove once one is saved. */
function ContactEmail({ saved }: { saved: string | null }) {
  const update = useUpdatePaperSources()
  const [draft, setDraft] = useState(saved ?? '')
  const [problem, setProblem] = useState<string | null>(null)

  function save(event: FormEvent) {
    event.preventDefault()
    const found = emailProblem(draft)
    setProblem(found)
    if (!found) update.mutate({ contact_email: draft.trim() })
  }

  function remove() {
    setDraft('')
    setProblem(null)
    update.mutate({ contact_email: null })
  }

  const unchanged = draft.trim() === '' || draft.trim() === saved
  return (
    <div className="grid gap-1.5">
      <Label htmlFor="paper-sources-email">Contact email</Label>
      {/* noValidate: the browser's own email check would stop the submit before emailProblem can explain it. */}
      <form noValidate className="flex gap-2" onSubmit={save}>
        <Input
          id="paper-sources-email"
          type="email"
          autoComplete="email"
          className="max-w-sm"
          value={draft}
          aria-invalid={problem !== null}
          aria-describedby={
            problem ? 'paper-sources-email-problem paper-sources-email-help' : 'paper-sources-email-help'
          }
          onChange={(event) => {
            setDraft(event.target.value)
            setProblem(null)
          }}
        />
        <Button type="submit" variant="outline" disabled={update.isPending || unchanged}>
          Save
        </Button>
        {saved !== null && (
          <Button type="button" variant="ghost" disabled={update.isPending} onClick={remove}>
            Remove
          </Button>
        )}
      </form>
      {problem && (
        <p id="paper-sources-email-problem" role="alert" className="text-xs text-destructive">
          {problem}
        </p>
      )}
      <p id="paper-sources-email-help" className="text-xs text-muted-foreground">
        Sent to Crossref and Unpaywall, and to OpenAlex when it's on. Unpaywall needs it.
      </p>
      {update.error && (
        <Alert variant="destructive" className="border-glass-border">
          <AlertDescription>{update.error.message}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}

/** The "Paper sources" section: which services Find papers and Similar ask, their API keys, and the contact email. */
export function PaperSourcesSettings() {
  const sources = usePaperSources()

  return (
    <section aria-labelledby="paper-sources-heading" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 id="paper-sources-heading" className="font-heading text-xl font-semibold">
          Paper sources
        </h2>
        <p className="text-sm text-muted-foreground">
          Find papers and Similar ask the sources that are on. What you search for is sent to each of them.
        </p>
      </div>

      {sources.data === undefined ? (
        sources.isError ? (
          <Alert variant="destructive" className="border-glass-border">
            <AlertDescription>{sources.error.message}</AlertDescription>
            <AlertAction>
              <Button variant="outline" size="xs" onClick={() => void sources.refetch()}>
                Retry
              </Button>
            </AlertAction>
          </Alert>
        ) : (
          <p className="text-muted-foreground">Loading…</p>
        )
      ) : (
        <>
          <ContactEmail saved={sources.data.contact_email} />
          <ul className={cn(glass, 'divide-y divide-glass-border rounded-xl ring-1 ring-glass-border')}>
            {sources.data.sources.map((source) => (
              <PaperSourceRow key={source.id} source={source} hasEmail={sources.data.contact_email !== null} />
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
