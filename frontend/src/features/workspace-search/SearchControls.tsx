import { useState } from 'react'
import { usePaperSources } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { SearchRunCreate, SearchSource } from '@/api/client'

// Search/discovery sources only (spec §6) — mirrors the backend's SearchSource Literal. Unpaywall is DOI-only PDF
// enrichment, never fanned out to by search_batch, so it's excluded here regardless of its own settings switch
// (C1: sending it used to 422 every Start click).
const SEARCH_SOURCE_IDS: readonly SearchSource[] = ['arxiv', 'crossref', 'core', 'semantic_scholar', 'openalex']

function isSearchSource(id: string): id is SearchSource {
  return (SEARCH_SOURCE_IDS as readonly string[]).includes(id)
}

export function SearchControls({
  onStart,
  onStop,
  isRunning,
}: {
  onStart: (args: SearchRunCreate) => void
  onStop?: () => void
  isRunning: boolean
}) {
  const [query, setQuery] = useState('')
  const paperSources = usePaperSources()
  // undefined until usePaperSources resolves, so Start stays disabled rather than sending an empty/wrong list.
  const enabledSources = paperSources.data?.sources
    .filter((source) => source.enabled && isSearchSource(source.id))
    .map((source) => source.id as SearchSource)

  return (
    <div className="flex items-center gap-2 border-b p-3">
      <label htmlFor="search-query" className="sr-only">
        Search query
      </label>
      <Input
        id="search-query"
        aria-label="Search query"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="e.g. large language model AND code review"
        disabled={isRunning}
      />
      {isRunning ? (
        <Button variant="destructive" onClick={onStop}>
          Stop
        </Button>
      ) : (
        <Button
          onClick={() => onStart({ query, filters: {}, sources: enabledSources!, query_overrides: {} })}
          disabled={!query || !enabledSources || enabledSources.length === 0}
        >
          Start
        </Button>
      )}
    </div>
  )
}
