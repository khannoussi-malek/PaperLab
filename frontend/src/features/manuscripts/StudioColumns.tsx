import { ChevronsLeft, ChevronsRight } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { loadPanelWidth, panelTrack, savePanelWidth, clampPanelWidth, type PanelLimits } from '@/components/panelWidth'
import { PanelResizeHandle } from '@/components/PanelResizeHandle'
import { browserStorage } from '@/features/notes/highlightColors'

/** One column of the studio. No `limits` = the flexible one (the editor). A function `content` gets the column's width in px. */
export type StudioColumn = { id: string; label: string; content: ReactNode | ((width: number) => ReactNode); limits?: PanelLimits }

const COLLAPSED_KEY = 'paperlab-studio-collapsed'
const RAIL = '2rem'

function loadCollapsed(): string[] {
  try {
    const parsed: unknown = JSON.parse(browserStorage()?.getItem(COLLAPSED_KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === 'string') : []
  } catch {
    return []
  }
}

/** Resizable, collapsible columns side by side. F6 / Shift+F6 move focus between the open ones. */
export function StudioColumns({ columns }: { columns: StudioColumn[] }) {
  const root = useRef<HTMLDivElement>(null)
  const [collapsed, setCollapsed] = useState(loadCollapsed)
  const [widths, setWidths] = useState(() =>
    Object.fromEntries(columns.flatMap((c) => (c.limits ? [[c.id, loadPanelWidth(c.limits, browserStorage())]] : []))),
  )
  useEffect(() => {
    try { browserStorage()?.setItem(COLLAPSED_KEY, JSON.stringify(collapsed)) } catch { /* ponytail: blocked storage only loses the choice */ }
  }, [collapsed])
  useEffect(() => columns.forEach((c) => c.limits && widths[c.id] !== undefined && savePanelWidth(c.limits, browserStorage(), widths[c.id])), [widths]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'F6' || e.altKey || e.ctrlKey || e.metaKey) return
      const regions = [...(root.current?.querySelectorAll<HTMLElement>('[data-studio-region]:not([hidden])') ?? [])]
      if (regions.length === 0) return
      e.preventDefault()
      const n = regions.length
      const at = regions.findIndex((r) => r.contains(document.activeElement))
      regions[at === -1 ? (e.shiftKey ? n - 1 : 0) : (at + (e.shiftKey ? -1 : 1) + n) % n].focus()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const toggle = (id: string) => setCollapsed((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]))
  const open = columns.filter((c) => !collapsed.includes(c.id))
  const flexId = (open.find((c) => !c.limits) ?? open[open.length - 1])?.id // the column that takes what is left
  const editorAt = columns.findIndex((c) => !c.limits)
  const width = (c: StudioColumn) => (c.limits ? clampPanelWidth(c.limits, widths[c.id], window.innerWidth) : 0)
  const track = (c: StudioColumn) =>
    collapsed.includes(c.id) ? RAIL : c.id === flexId || !c.limits ? 'minmax(0,1fr)' : panelTrack(c.limits, widths[c.id])

  return (
    <div ref={root} className="grid min-h-0 flex-1 overflow-hidden" style={{ gridTemplateColumns: columns.map(track).join(' ') }}>
      {columns.map((c, i) => {
        const isCollapsed = collapsed.includes(c.id)
        const before = editorAt !== -1 && i < editorAt
        return (
          <div key={c.id} className="contents">
            {isCollapsed && (
              <div className={`flex min-h-0 flex-col items-center gap-2 bg-muted/40 py-1 ${before ? 'border-r' : 'border-l'} border-glass-border`}>
                <button type="button" aria-expanded={false} aria-label={`Expand ${c.label}`} title={`Expand ${c.label}`}
                  onClick={() => toggle(c.id)}
                  className="rounded-md p-1 text-muted-foreground outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50">
                  {before ? <ChevronsRight aria-hidden className="size-4" /> : <ChevronsLeft aria-hidden className="size-4" />}
                </button>
                <span aria-hidden className="text-xs uppercase tracking-wide text-muted-foreground [writing-mode:vertical-rl]">{c.label}</span>
              </div>
            )}
            <section
              data-studio-region
              role="region"
              aria-label={c.label}
              tabIndex={-1}
              hidden={isCollapsed}
              className={`relative flex min-h-0 min-w-0 flex-col outline-none focus-visible:ring-3 focus-visible:ring-ring/50 ${before ? 'border-r' : i > editorAt && editorAt !== -1 ? 'border-l' : ''} border-glass-border`}
            >
              {c.limits && c.id !== flexId && (
                <PanelResizeHandle limits={c.limits} width={width(c)} onWidthChange={(w) => setWidths((all) => ({ ...all, [c.id]: w }))}
                  label={`Resize ${c.label}`} edge={before ? 'right' : 'left'} />
              )}
              <div className="flex h-6 shrink-0 justify-end px-1">
                <button type="button" aria-expanded aria-label={`Collapse ${c.label}`} title={`Collapse ${c.label}`}
                  onClick={() => toggle(c.id)}
                  className="rounded-md px-1 text-muted-foreground outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50">
                  {before ? <ChevronsLeft aria-hidden className="size-3.5" /> : <ChevronsRight aria-hidden className="size-3.5" />}
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-hidden">{typeof c.content === 'function' ? c.content(width(c)) : c.content}</div>
            </section>
          </div>
        )
      })}
    </div>
  )
}
