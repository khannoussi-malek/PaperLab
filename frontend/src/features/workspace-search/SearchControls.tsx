import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { SearchRunCreate } from '@/api/client'

const DEFAULT_SOURCES = ['arxiv', 'crossref', 'core', 'semantic_scholar', 'unpaywall']

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
          onClick={() => onStart({ query, filters: {}, sources: DEFAULT_SOURCES, query_overrides: {} })}
          disabled={!query}
        >
          Start
        </Button>
      )}
    </div>
  )
}
