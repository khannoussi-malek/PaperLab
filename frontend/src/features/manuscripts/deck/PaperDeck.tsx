import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { cardTransform, windowAround, type DeckPaper } from './deckModel'

const FLIP_MS = 500
const WHEEL_GAP_MS = 120

export type PaperDeckProps = {
  papers: DeckPaper[]
  current: number
  onCurrent: (i: number) => void
  onOpen: (i: number) => void
  filter: string
  onFilter: (s: string) => void
  /** Accessible name of the deck, e.g. "Papers". */
  label: string
  /** Paper KEYS (the cite keys, `DeckPaper.key`) that get a "cited" tag. */
  cited?: Set<string>
}

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

function reducedMotion(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
}

function byline(p: DeckPaper): string {
  return [p.first_author, p.year].filter(Boolean).join(' ')
}

function announce(p: DeckPaper, i: number, n: number): string {
  const parts = [byline(p) || p.title]
  if (p.notes) parts.push(plural(p.notes, 'note'))
  if (p.highlights) parts.push(plural(p.highlights, 'highlight'))
  if (p.ai_notes) parts.push(plural(p.ai_notes, 'AI note'))
  parts.push(`paper ${i + 1} of ${n}`)
  return parts.join(', ')
}

const BADGE = 'rounded px-1.5 py-px font-sans text-[9px]'

function Card({ paper, offset, cited, still, onClick }: { paper: DeckPaper; offset: number; cited: boolean; still: boolean; onClick: () => void }) {
  const { transform, zIndex, opacity } = cardTransform(offset)
  return (
    <div
      data-deck-card={paper.paper_id}
      aria-hidden="true"
      onClick={onClick}
      style={{ transform, zIndex, opacity, transition: still ? 'none' : `transform ${FLIP_MS}ms cubic-bezier(.2,.8,.2,1), opacity ${FLIP_MS}ms` }}
      className="absolute left-1/2 top-10 -ml-[75px] h-[205px] w-[150px] cursor-pointer rounded-md bg-white p-3 font-serif text-[10px] text-neutral-800 shadow-[0_10px_26px_rgba(0,0,0,.22)] [backface-visibility:hidden]"
    >
      <b className="mb-1.5 block line-clamp-4 text-xs">{paper.title}</b>
      <div className="mb-2 text-neutral-500">{byline(paper)}</div>
      {[78, 92, 66, 85, 70, 95, 74, 88, 62].map((w, i) => (
        <div key={i} className="my-1 h-1 rounded-sm bg-neutral-200" style={{ width: `${w}%` }} />
      ))}
      <div className="absolute inset-x-3 bottom-2.5 flex gap-1">
        {paper.notes > 0 && <span className={`${BADGE} bg-yellow-100 text-yellow-900`}>{paper.notes} N</span>}
        {paper.highlights > 0 && <span className={`${BADGE} bg-yellow-100 text-yellow-900`}>{paper.highlights} H</span>}
        {paper.ai_notes > 0 && <span className={`${BADGE} bg-purple-100 text-purple-900`}>{paper.ai_notes} A</span>}
        {cited && <span className={`${BADGE} bg-neutral-200 text-neutral-700`}>cited</span>}
      </div>
    </div>
  )
}

/** A controlled 3D deck of papers. It knows nothing about manuscripts: the parent filters, orders and owns `current`. */
export function PaperDeck({ papers, current, onCurrent, onOpen, filter, onFilter, label, cited }: PaperDeckProps) {
  const [still] = useState(reducedMotion)
  const stage = useRef<HTMLDivElement>(null)
  const last = papers.length - 1
  const go = (i: number) => {
    const next = Math.max(0, Math.min(last, i))
    if (next !== current) onCurrent(next)
  }

  // A non-passive wheel listener, so the page does not scroll while the deck flips.
  const live = useRef({ go, current })
  live.current = { go, current }
  const lastWheel = useRef(0)
  useEffect(() => {
    const el = stage.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      if (e.timeStamp - lastWheel.current < WHEEL_GAP_MS) return
      lastWheel.current = e.timeStamp
      live.current.go(live.current.current + (e.deltaY > 0 ? 1 : -1))
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [papers.length])

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.ctrlKey || e.metaKey || e.altKey || !papers.length) return
    const k = e.key
    if (k === 'ArrowRight') go(current + 1)
    else if (k === 'ArrowLeft') go(current - 1)
    else if (k === 'Home') go(0)
    else if (k === 'End') go(last)
    else if (k === 'Enter' || k === ' ') onOpen(current)
    else if (/^[a-z]$/i.test(k)) {
      const j = papers.findIndex((p, i) => i !== current && p.title.toLowerCase().startsWith(k.toLowerCase()))
      if (j < 0) return
      go(j)
    } else return
    e.preventDefault()
  }

  const searchBox = (
    <input
      type="search"
      aria-label="Search papers"
      placeholder="Search papers"
      value={filter}
      onChange={(e) => onFilter(e.target.value)}
      className="mb-2 h-8 w-full rounded-md border border-input bg-background px-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    />
  )

  if (!papers.length) {
    return (
      <div>
        {searchBox}
        <p className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
          {filter ? 'No paper matches' : 'No papers in this workspace yet'}
        </p>
      </div>
    )
  }

  return (
    <div>
      {searchBox}
      <div
        ref={stage}
        role="group"
        aria-roledescription="paper deck"
        aria-label={label}
        tabIndex={0}
        onKeyDown={onKeyDown}
        className="relative h-[340px] select-none overflow-hidden rounded-lg border border-border bg-background [perspective:1400px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <div className="absolute inset-0 [transform-style:preserve-3d]">
          {windowAround(papers.length, current).map((i) => (
            <Card
              key={papers[i].paper_id}
              paper={papers[i]}
              offset={i - current}
              cited={!!cited?.has(papers[i].key)}
              still={still}
              onClick={() => (i === current ? onOpen(i) : go(i))}
            />
          ))}
        </div>
        <div className="absolute inset-x-0 bottom-2.5 flex items-center justify-center gap-2 text-xs text-muted-foreground">
          <button type="button" aria-label="Previous paper" disabled={current <= 0} onClick={() => go(current - 1)} className="rounded-md border border-border bg-secondary p-1 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40">
            <ChevronLeft className="size-4" />
          </button>
          <span className="tabular-nums">{current + 1} / {papers.length}</span>
          <button type="button" aria-label="Next paper" disabled={current >= last} onClick={() => go(current + 1)} className="rounded-md border border-border bg-secondary p-1 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40">
            <ChevronRight className="size-4" />
          </button>
        </div>
      </div>
      <p role="status" aria-live="polite" className="sr-only">{announce(papers[current], current, papers.length)}</p>
    </div>
  )
}
