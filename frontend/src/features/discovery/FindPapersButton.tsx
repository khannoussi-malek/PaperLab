import { Search } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { useSearchPapers } from '@/api/queries'
import { glass } from '@/components/glass'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { ErrorAlert } from '@/features/library/ErrorAlert'
import { cn } from '@/lib/utils'
import { CandidateList } from './CandidateList'

const QUERY_LABEL = 'Title, DOI, arXiv ID or OpenAlex ID'

/** "Find papers" and its dialog: search outside the library, then add a paper that has a free PDF. */
export function FindPapersButton({ workspaceId }: { workspaceId?: string }) {
  const [draft, setDraft] = useState('')
  const [query, setQuery] = useState<string | null>(null)
  const results = useSearchPapers(query)

  function submit(event: FormEvent) {
    event.preventDefault()
    if (draft.trim()) setQuery(draft.trim())
  }

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline">
          <Search aria-hidden />
          Find papers
        </Button>
      </DialogTrigger>
      <DialogContent className={cn(glass, 'bg-glass-strong ring-glass-border sm:max-w-2xl')}>
        <DialogHeader>
          <DialogTitle>Find papers</DialogTitle>
          <DialogDescription>
            Search by title or identifier. Add downloads a free PDF only: from arXiv, a repository or an open-access
            publisher.
          </DialogDescription>
        </DialogHeader>
        <form className="flex gap-2" onSubmit={submit}>
          <Input
            aria-label={QUERY_LABEL}
            placeholder={QUERY_LABEL}
            maxLength={500}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
          <Button type="submit" disabled={!draft.trim() || results.isFetching}>
            {results.isFetching ? 'Searching…' : 'Search'}
          </Button>
        </form>
        {query !== null && (
          <div className="max-h-[60vh] min-h-0 overflow-y-auto">
            {results.isError ? (
              <ErrorAlert message={results.error.message} />
            ) : results.data === undefined ? (
              <p className="text-muted-foreground">Searching…</p>
            ) : (
              <CandidateList
                candidates={results.data}
                empty="No papers found. Try the exact title, a DOI or an arXiv ID."
                workspaceId={workspaceId}
              />
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
