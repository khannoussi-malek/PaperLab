import { Fragment } from 'react'
import type { ProvenanceOut } from '@/api/client'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { collapse, type NavEntry } from './navPath'

const SEPARATOR: Partial<Record<NavEntry['via'], string>> = { cites: 'it cites', cited_by: 'cited by' }

function labelOf(id: string, data: ProvenanceOut): string {
  if (id === 'root:hand') return 'Added by hand'
  const root = data.roots.find((r) => r.id === id)
  if (root) return `🔍 ${root.label}`
  if (id.startsWith('root:')) return `🔍 ${id.slice(5)}`
  return data.nodes.find((n) => n.id === id)?.title ?? 'a paper'
}

type Props = { path: NavEntry[]; data: ProvenanceOut; onGo: (index: number) => void }

/** The walk so far. Long paths show the first entry, a `…` menu with the hidden ones, and the last two. */
export function Breadcrumb({ path, data, onGo }: Props) {
  const shown = collapse(path)
  const hiddenFrom = 1
  const hiddenTo = path.length - 2
  const entryButton = (index: number) => (
    <button type="button" onClick={() => onGo(index)} className={`min-w-0 truncate rounded px-1 hover:bg-muted ${index === path.length - 1 ? 'shrink' : 'shrink-[4]'}`} title={labelOf(path[index].id, data)} aria-current={index === path.length - 1 ? 'page' : undefined}>
      {labelOf(path[index].id, data)}
    </button>
  )
  return (
    <nav aria-label="Snowball path" className="flex min-w-0 items-center gap-1 overflow-hidden whitespace-nowrap text-sm">
      {shown.map((item, i) => {
        // `item` is the entry itself or 'more'; its index in `path` is fixed by where it sits in the collapsed list.
        const index = item === 'more' ? -1 : shown.length === path.length ? i : i === 0 ? 0 : path.length - (shown.length - i)
        const via = item === 'more' ? undefined : path[index].via
        return (
          <Fragment key={i}>
            {i > 0 && <span aria-hidden className="shrink-0 text-muted-foreground">›</span>}
            {via && SEPARATOR[via] && i > 0 && <span className="shrink-0 text-xs italic text-muted-foreground">{SEPARATOR[via]}</span>}
            {item === 'more' ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button type="button" aria-label={`Show ${hiddenTo - hiddenFrom} earlier steps`} className="shrink-0 rounded px-1 hover:bg-muted">…</button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  {path.slice(hiddenFrom, hiddenTo).map((e, k) => (
                    <DropdownMenuItem key={hiddenFrom + k} onSelect={() => onGo(hiddenFrom + k)}>{labelOf(e.id, data)}</DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              entryButton(index)
            )}
          </Fragment>
        )
      })}
    </nav>
  )
}
