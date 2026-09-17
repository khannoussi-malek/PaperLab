import { Link2, Pencil, Trash2 } from 'lucide-react'
import type { GraphLink, GraphNode } from '@/api/client'
import { Button } from '@/components/ui/button'
import { readerHref } from '@/lib/route'
import { KIND_LABELS, KINDS } from './graphModel'

type Props = {
  nodes: GraphNode[]
  /** The visible links only: the panel says exactly what the canvas draws. */
  links: GraphLink[]
  focused: GraphNode | null
  onFocus: (paperId: string) => void
  onClear: () => void
  onAddLink: () => void
  onEditLink: (link: GraphLink) => void
  onRemoveLink: (link: GraphLink) => void
}

/** A paper's connections by kind, plus the papers list. D108: the canvas is hidden, so this is the interface. */
export function GraphPanel({ nodes, links, focused, onFocus, onClear, onAddLink, onEditLink, onRemoveLink }: Props) {
  const byId = new Map(nodes.map((node) => [node.id, node]))
  const degree = new Map<string, number>()
  for (const link of links) {
    degree.set(link.source, (degree.get(link.source) ?? 0) + 1)
    degree.set(link.target, (degree.get(link.target) ?? 0) + 1)
  }

  if (focused === null) {
    const sorted = [...nodes].sort(
      (a, b) => (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0) || a.title.localeCompare(b.title)
    )
    return (
      <section aria-labelledby="graph-papers" className="flex min-h-0 flex-col gap-2">
        <h2 id="graph-papers" className="text-sm font-medium">
          Papers
        </h2>
        <ul className="flex min-h-0 flex-col gap-1 overflow-y-auto">
          {sorted.map((node) => (
            <li key={node.id}>
              <button
                type="button"
                className="graph-paper flex w-full items-baseline gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted"
                data-paper-id={node.id}
                onClick={() => onFocus(node.id)}
              >
                <span className="truncate" title={node.title}>
                  {node.title}
                </span>
                <span className="ml-auto shrink-0 text-muted-foreground">{degree.get(node.id) ?? 0}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    )
  }

  const connections = links.filter((link) => link.source === focused.id || link.target === focused.id)
  const other = (link: GraphLink) => (link.source === focused.id ? link.target : link.source)

  return (
    <section aria-labelledby="graph-connections" className="flex min-h-0 flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 id="graph-connections" className="text-sm font-medium">
            Connected papers
          </h2>
          <p className="truncate text-sm text-muted-foreground" title={focused.title}>
            {focused.title}
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={onClear}>
          Clear focus
        </Button>
      </div>

      <Button variant="outline" size="sm" className="self-start" onClick={onAddLink}>
        <Link2 aria-hidden />
        Link to another paper…
      </Button>

      <div className="flex min-h-0 flex-col gap-4 overflow-y-auto">
        {connections.length === 0 && (
          <p className="text-sm text-muted-foreground">No links in the layers you have on.</p>
        )}
        {KINDS.map((kind) => {
          const rows = connections.filter((link) => link.kind === kind)
          if (rows.length === 0) return null
          return (
            <section key={kind} aria-labelledby={`graph-kind-${kind}`} className="flex flex-col gap-1">
              <h3 id={`graph-kind-${kind}`} className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                {KIND_LABELS[kind]}
              </h3>
              <ul className="flex flex-col gap-1">
                {rows.map((link) => {
                  const paper = byId.get(other(link))
                  if (!paper) return null
                  return (
                    <li key={`${kind}-${link.id ?? other(link)}`} className="graph-connection flex items-center gap-1">
                      <a
                        href={readerHref(paper.id)}
                        className="min-w-0 flex-1 truncate rounded-md px-2 py-1.5 text-sm hover:bg-muted"
                        title={paper.title}
                        data-paper-id={paper.id}
                      >
                        {paper.title}
                        {link.label && <span className="text-muted-foreground"> — {link.label}</span>}
                      </a>
                      {kind === 'manual' && (
                        <>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Edit label for ${paper.title}`}
                            onClick={() => onEditLink(link)}
                          >
                            <Pencil aria-hidden />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Remove link to ${paper.title}`}
                            onClick={() => onRemoveLink(link)}
                          >
                            <Trash2 aria-hidden />
                          </Button>
                        </>
                      )}
                    </li>
                  )
                })}
              </ul>
            </section>
          )
        })}
      </div>
    </section>
  )
}
