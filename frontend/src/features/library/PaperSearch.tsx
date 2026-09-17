import { Search, SearchX, X } from 'lucide-react'
import type { Ref } from 'react'
import { glass } from '@/components/glass'
import { popIn, pressable } from '@/components/motion'
import { Button } from '@/components/ui/button'
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from '@/components/ui/input-group'
import { cn } from '@/lib/utils'

type SearchProps = {
  query: string
  shown: number
  total: number
  inputRef: Ref<HTMLInputElement>
  onQueryChange: (query: string) => void
  /** Empties the query and puts the cursor back in the field (the clear button unmounts with the query). */
  onClear: () => void
}

/** The paper list's search bar: glass, with "3 of 18" and a clear button popping in while a search is on. */
export function PaperSearch({ query, shown, total, inputRef, onQueryChange, onClear }: SearchProps) {
  const searching = query.trim() !== ''
  return (
    <InputGroup
      className={cn(
        glass,
        'h-10 rounded-xl border-glass-border transition-[border-color,box-shadow] duration-200 dark:bg-glass',
      )}
    >
      <InputGroupAddon>
        <Search aria-hidden className="transition-colors duration-200 group-focus-within/input-group:text-primary" />
      </InputGroupAddon>
      <InputGroupInput
        ref={inputRef}
        type="search"
        aria-label="Search papers"
        placeholder="Search by title, author, year or venue"
        value={query}
        onChange={(event) => onQueryChange(event.target.value)}
        onKeyDown={(event) => event.key === 'Escape' && onQueryChange('')}
        // The browser's own clear icon doesn't match the theme; the button below replaces it.
        className="[&::-webkit-search-cancel-button]:appearance-none"
      />
      <InputGroupAddon align="inline-end">
        {/* Mounted before any search, so screen readers announce each new count. No aria-label: some would read it
            instead of the count. */}
        <span role="status" className="search-count text-xs tabular-nums">
          {searching && (
            <span className={cn('inline-block origin-right', popIn)}>
              {`${shown} of ${total}`}
              <span className="sr-only"> papers</span>
            </span>
          )}
        </span>
        {searching && (
          <InputGroupButton
            size="icon-xs"
            aria-label="Clear search"
            title="Clear search"
            className={cn('origin-center', popIn, pressable)}
            onClick={onClear}
          >
            <X aria-hidden />
          </InputGroupButton>
        )}
      </InputGroupAddon>
    </InputGroup>
  )
}

/** Shown in place of the rows when nothing matches: says so, suggests what to try, and offers the way back. */
export function NoMatches({ query, onClear }: { query: string; onClear: () => void }) {
  return (
    <div
      className={cn(
        'no-matches grid origin-top place-items-center gap-3 rounded-xl border border-dashed border-glass-border px-6 py-14 text-center',
        popIn,
      )}
    >
      <SearchX aria-hidden className="size-8 text-muted-foreground" />
      <div className="flex flex-col gap-1">
        <p className="font-medium wrap-anywhere">No papers match “{query.trim()}”</p>
        <p className="text-sm text-muted-foreground">Check the spelling, or try an author's surname or a year.</p>
      </div>
      <Button variant="outline" size="sm" className={pressable} onClick={onClear}>
        Clear search
      </Button>
    </div>
  )
}
