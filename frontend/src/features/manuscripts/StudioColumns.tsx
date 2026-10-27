import { ChevronsLeft, ChevronsRight } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { loadPanelWidth, panelTrack, savePanelWidth, clampPanelWidth, type PanelLimits } from '@/components/panelWidth'
import { PanelResizeHandle } from '@/components/PanelResizeHandle'
import { browserStorage } from '@/features/notes/highlightColors'

/** One column of the studio. No `limits` = the flexible one (the editor). A function `content` gets the column's width in px. */
export type StudioColumn = {
  id: string
  label: string
  content: ReactNode | ((width: number) => ReactNode)
  limits?: PanelLimits
  /** Below NARROW_PX this column and the one with this id share one column as two tabs (this column's tab first). */
  shareWith?: string
}

const NARROW_PX = 1280
const TAB_KEY = 'paperlab-studio-tab'

function useNarrow() {
  const [narrow, setNarrow] = useState(() => window.innerWidth < NARROW_PX)
  useEffect(() => {
    const onResize = () => setNarrow(window.innerWidth < NARROW_PX)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  return narrow
}

/** Both panels stay mounted (a deck or a PDF keeps its state); only the active one shows. */
function SharedTabs({ tabs, active, onActive }: { tabs: { id: string; label: string; body: ReactNode }[]; active: string; onActive: (id: string) => void }) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div role="tablist" className="flex shrink-0 gap-1 border-b border-glass-border px-2">
        {tabs.map((t) => (
          <button key={t.id} type="button" role="tab" id={`studio-tab-${t.id}`} aria-selected={t.id === active} aria-controls={`studio-panel-${t.id}`}
            onClick={() => onActive(t.id)}
            className={`-mb-px border-b-2 px-2 py-1 text-xs outline-none focus-visible:ring-3 focus-visible:ring-ring/50 ${t.id === active ? 'border-primary font-medium' : 'border-transparent text-muted-foreground'}`}>
            {t.label}
          </button>
        ))}
      </div>
      {tabs.map((t) => (
        <div key={t.id} role="tabpanel" id={`studio-panel-${t.id}`} aria-labelledby={`studio-tab-${t.id}`} hidden={t.id !== active} className="min-h-0 flex-1 overflow-hidden">
          {t.body}
        </div>
      ))}
    </div>
  )
}

const COLLAPSED_KEY = 'paperlab-studio-collapsed'
const RAIL = '2rem'
const RAIL_PX = 32
/** The editor never gets less than this; when the fixed columns would leave it less, the PDF and Papers share a column. */
const EDITOR_MIN = 420

function loadCollapsed(): string[] {
  try {
    const parsed: unknown = JSON.parse(browserStorage()?.getItem(COLLAPSED_KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === 'string') : []
  } catch {
    return []
  }
}

/** Resizable, collapsible columns side by side. F6 / Shift+F6 move focus between the open ones. */
export function StudioColumns({ columns: all, reveal }: { columns: StudioColumn[]; reveal?: { id: string; n: number } }) {
  const [activeTab, setActiveTab] = useState(() => { try { return browserStorage()?.getItem(TAB_KEY) ?? '' } catch { return '' } })
  useEffect(() => { try { browserStorage()?.setItem(TAB_KEY, activeTab) } catch { /* ponytail: blocked storage only loses the choice */ } }, [activeTab])
  const root = useRef<HTMLDivElement>(null)
  const [collapsed, setCollapsed] = useState(loadCollapsed)
  const [widths, setWidths] = useState(() =>
    Object.fromEntries(all.flatMap((c) => (c.limits ? [[c.id, loadPanelWidth(c.limits, browserStorage())]] : []))),
  )
  useEffect(() => {
    try { browserStorage()?.setItem(COLLAPSED_KEY, JSON.stringify(collapsed)) } catch { /* ponytail: blocked storage only loses the choice */ }
  }, [collapsed])
  useEffect(() => all.forEach((c) => c.limits && widths[c.id] !== undefined && savePanelWidth(c.limits, browserStorage(), widths[c.id])), [widths]) // eslint-disable-line react-hooks/exhaustive-deps

  // The studio's own width decides, not the window's: the app rail and the saved column widths both take room.
  // Until the first measurement, the window width is the guess.
  const guess = useNarrow()
  const [room, setRoom] = useState<number | null>(null)
  useEffect(() => {
    const el = root.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver((entries) => setRoom(entries[entries.length - 1].contentRect.width))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  const fixed = all.reduce(
    (sum, c) => sum + (!c.limits ? 0 : collapsed.includes(c.id) ? RAIL_PX : clampPanelWidth(c.limits, widths[c.id] ?? c.limits.defaultWidth, window.innerWidth)),
    0,
  )
  const narrow = room === null ? guess : fixed + EDITOR_MIN > room
  const columns = narrow ? all.flatMap((c): StudioColumn[] => {
    const partner = all.find((o) => o.id === c.shareWith)
    if (partner) {
      const parts = [c, partner]
      const active = parts.some((p) => p.id === activeTab) ? activeTab : c.id
      return [{ ...c, label: `${c.label} and ${partner.label}`, content: (w) => (
        <SharedTabs active={active} onActive={setActiveTab}
          tabs={parts.map((p) => ({ id: p.id, label: p.label, body: typeof p.content === 'function' ? p.content(w) : p.content }))} />
      ) }]
    }
    return all.some((o) => o.shareWith === c.id) ? [] : [c]
  }) : all

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

  useEffect(() => {
    if (!reveal) return
    const host = narrow ? (all.find((c) => c.shareWith === reveal.id)?.id ?? reveal.id) : reveal.id // narrow: the column it shares
    if (narrow) setActiveTab(reveal.id)
    setCollapsed((c) => c.filter((x) => x !== reveal.id && x !== host))
  }, [reveal?.n]) // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (id: string) => setCollapsed((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]))
  const open = columns.filter((c) => !collapsed.includes(c.id))
  const flexId = (open.find((c) => !c.limits) ?? open[open.length - 1])?.id // the column that takes what is left
  const editorAt = columns.findIndex((c) => !c.limits)
  const width = (c: StudioColumn) => (c.limits ? clampPanelWidth(c.limits, widths[c.id] ?? c.limits.defaultWidth, window.innerWidth) : 0)
  const track = (c: StudioColumn) =>
    collapsed.includes(c.id) ? RAIL : !c.limits && !narrow ? `minmax(${EDITOR_MIN}px,1fr)` : c.id === flexId || !c.limits ? 'minmax(0,1fr)' : panelTrack(c.limits, widths[c.id] ?? c.limits.defaultWidth)

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
