import { X } from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { startPaperDrag } from '../citeCompletion'
import { insertText, turnDirection, type BookItem, type DeckPaper, type VerdictView } from './deckModel'
import { PAGE_CLASS, turnLeaf } from './pageTurn'
import { useReducedMotion } from './useReducedMotion'

export type PaperBookProps = {
  paper: DeckPaper
  items: BookItem[]
  selected: number
  onSelect: (i: number) => void
  /** `null` = insert just the paper's \citep. The parent does the inserting. */
  onInsert: (item: BookItem | null) => void
  onOpenReader: (item: BookItem | null) => void
  onClose: () => void
  /** Evidence mode: what the model said about this paper, shown under a selected passage. */
  verdict?: VerdictView | null
}

const KIND = {
  highlight: { name: 'Your highlight', letter: 'H', tab: 'bg-yellow-300 text-yellow-950', mark: 'bg-yellow-200', chip: 'bg-yellow-100 text-yellow-900' },
  note: { name: 'Your note', letter: 'N', tab: 'bg-yellow-300 text-yellow-950', mark: 'bg-yellow-200', chip: 'bg-yellow-100 text-yellow-900' },
  ai: { name: 'AI note', letter: 'A', tab: 'bg-purple-300 text-purple-950', mark: 'bg-purple-200', chip: 'bg-purple-100 text-purple-900' },
  evidence: { name: 'Evidence passage', letter: 'E', tab: 'bg-blue-300 text-blue-950', mark: 'bg-blue-200', chip: 'bg-blue-100 text-blue-900' },
} as const

const insertLabel = (item: BookItem) =>
  item.kind === 'evidence' ? 'Cite this paper' : item.kind === 'ai' ? 'Insert as comment' : item.kind === 'highlight' ? 'Insert quote + \\citep' : 'Insert note + \\citep'

const announce = (items: BookItem[], i: number) => {
  const it = items[i]
  if (!it) return 'No notes on this paper yet.'
  return `${KIND[it.kind].name}${it.page != null ? `, page ${it.page}` : ''}: ${it.text}. ${i + 1} of ${items.length}.`
}

const byline = (p: DeckPaper) => [p.first_author, p.year].filter(Boolean).join(' · ')
const RULE = [62, 88, 70, 95, 66, 82, 74, 90, 68, 84, 72, 92, 64]
const Lines = ({ n, seed = 0 }: { n: number; seed?: number }) => (
  <>
    {Array.from({ length: n }, (_, i) => (
      <div key={i} className="my-1 h-1 rounded-sm bg-neutral-200" style={{ width: `${RULE[(i + seed) % RULE.length]}%` }} />
    ))}
  </>
)

const Cover = ({ paper }: { paper: DeckPaper }) => (
  <div className="-m-3.5 h-[260px] bg-[linear-gradient(135deg,#2f4f6f,#1f3550)] p-3.5 text-[#f3efe4]">
    <div className="mt-10 text-[13px] font-bold">{paper.title}</div>
    {byline(paper) && <div className="mt-2 opacity-75">{byline(paper)}</div>}
  </div>
)
const LeftPage = ({ item }: { item?: BookItem }) => (
  <>
    <div className="mb-1.5 text-[9px] text-neutral-400">{item?.page != null ? `p.${item.page - 1}` : ''}</div>
    <Lines n={13} seed={item?.page ?? 0} />
  </>
)
const RightPage = ({ item }: { item?: BookItem }) =>
  item ? (
    <>
      <div className="mb-1.5 text-right text-[9px] text-neutral-400">{item.page != null ? `p.${item.page}` : KIND[item.kind].name}</div>
      <Lines n={3} seed={item.page ?? 0} />
      <p className="my-1.5 leading-snug">
        <mark className={`${KIND[item.kind].mark} text-neutral-900`}>“{item.text}”</mark>
      </p>
      <Lines n={6} seed={(item.page ?? 0) + 3} />
    </>
  ) : (
    <p className="mt-16 text-center text-neutral-500">No notes on this paper yet</p>
  )

const html = (node: ReactNode) => renderToStaticMarkup(<>{node}</>)

type Pages = { l: number; r: number; lHidden: boolean }

export function PaperBook({ paper, items, selected, onSelect, onInsert, onOpenReader, onClose, verdict }: PaperBookProps) {
  const still = useReducedMotion()
  const root = useRef<HTMLDivElement>(null)
  const book = useRef<HTMLDivElement>(null)
  const turn = useRef<{ finish(): void } | null>(null)
  const sel = Math.min(Math.max(selected, 0), Math.max(items.length - 1, 0))
  const shown = useRef(sel)
  const mounted = useRef(false)
  useEffect(() => { // declared first, so its cleanup runs before the turn is finished on unmount
    mounted.current = true
    return () => { mounted.current = false }
  }, [])
  const [pages, setPages] = useState<Pages>({ l: sel, r: sel, lHidden: true })
  const live = useRef({ items, sel, still })
  live.current = { items, sel, still }

  // Opening: the cover turns over to the left.
  useEffect(() => {
    root.current?.focus()
    const { items: its, sel: s, still: st } = live.current
    const land = () => mounted.current && setPages((p) => ({ ...p, l: s, lHidden: false }))
    if (!its.length || !book.current) {
      setPages((p) => ({ ...p, lHidden: false }))
      return
    }
    turn.current = turnLeaf(book.current, 'fwd', html(<Cover paper={paper} />), html(<LeftPage item={its[s]} />), { still: st, land })
    return () => turn.current?.finish()
  }, [])

  // Selection changed (key, tab, list or the parent): turn to it, finishing any turn still running.
  useEffect(() => {
    const from = shown.current
    if (sel === from || !book.current || !items[sel]) return
    turn.current?.finish()
    shown.current = sel
    const dir = turnDirection(from, sel)
    const [a, b] = [items[from], items[sel]]
    const opts =
      dir === 'fwd'
        ? { uncover: () => mounted.current && setPages((p) => ({ ...p, r: sel })), land: () => mounted.current && setPages((p) => ({ ...p, l: sel })) }
        : { uncover: () => mounted.current && setPages((p) => ({ ...p, l: sel })), land: () => mounted.current && setPages((p) => ({ ...p, r: sel })) }
    turn.current = turnLeaf(
      book.current,
      dir,
      html(dir === 'fwd' ? <RightPage item={a} /> : <LeftPage item={a} />),
      html(dir === 'fwd' ? <LeftPage item={b} /> : <RightPage item={b} />),
      { ...opts, still },
    )
  }, [sel, items, still])

  const pick = (i: number) => {
    if (i >= 0 && i < items.length && i !== sel) onSelect(i)
  }
  const item = items[sel] ?? null

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return
    const k = e.key
    if (k === 'ArrowDown' || k === 'ArrowRight') pick(sel + 1)
    else if (k === 'ArrowUp' || k === 'ArrowLeft') pick(sel - 1)
    else if (k === 'i') onInsert(item)
    else if (k === 'o') onOpenReader(item)
    else if (k === 'Escape') onClose()
    else return
    e.preventDefault()
  }

  const btn =
    'rounded-md border border-border bg-secondary px-2 py-1 text-xs text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
  const rest = 'shadow-[0_14px_28px_rgba(0,0,0,.25)]'

  return (
    <div
      ref={root}
      tabIndex={0}
      role="group"
      aria-roledescription="paper book"
      aria-label={paper.title}
      onKeyDown={onKeyDown}
      className="rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="flex items-center justify-between gap-2 pb-1">
        <button type="button" onClick={onClose} className={`${btn} inline-flex items-center gap-1`}>
          <X className="size-3" aria-hidden /> Back to the deck
        </button>
        <button type="button" onClick={() => onOpenReader(item)} className={btn}>Open in reader</button>
      </div>
      <div className="relative h-[310px] overflow-hidden rounded-lg border border-border bg-background [perspective:1400px]">
        <div ref={book} className="absolute left-1/2 top-7 -ml-40 h-[260px] w-[320px] [transform-style:preserve-3d] [transform:rotateX(8deg)]">
          <div className={`${PAGE_CLASS} left-0 rounded-l ${rest} ${pages.lHidden ? 'invisible' : ''}`}>
            <LeftPage item={items[pages.l]} />
          </div>
          <div className={`${PAGE_CLASS} left-[160px] rounded-r ${rest}`}>
            <RightPage item={items[pages.r]} />
          </div>
          <div className="absolute -right-7 top-4 z-[8] flex flex-col gap-1.5">
            {items.map((it, j) => (
              <button
                key={it.id}
                type="button"
                data-book-tab={it.id}
                aria-label={`${KIND[it.kind].name}${it.page != null ? `, page ${it.page}` : ''}`}
                aria-current={j === sel ? 'true' : undefined}
                onClick={() => pick(j)}
                className={`flex h-[30px] w-7 items-center justify-center gap-px rounded-r-md text-[9px] shadow-md transition-transform hover:translate-x-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${KIND[it.kind].tab} ${j === sel ? 'translate-x-1' : ''}`}
              >
                <b>{KIND[it.kind].letter}</b>
                {it.page != null && <span>{it.page}</span>}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-2 text-sm">
        <div className="font-semibold">{paper.title}</div>
        <div className="mb-2 text-xs text-muted-foreground">{[byline(paper), `\\citep{${paper.key}}`].filter(Boolean).join(' · ')}</div>
        <button type="button" onClick={() => onInsert(null)} className={`${btn} mb-2`}>{`Insert \\citep{${paper.key}}`}</button>
        {!items.length && <p className="text-xs text-muted-foreground">No notes on this paper yet</p>}
        <ul className="space-y-1.5">
          {items.map((it, j) => (
            // An AI note is not draggable: a drop lands mid-line, where its comment would swallow the rest of the line.
            // Its Insert button puts it on lines of its own.
            <li key={it.id} draggable={it.kind !== 'ai'} onDragStart={(e) => { if (it.kind !== 'ai') startPaperDrag(e, paper.paper_id, insertText(it, paper.key)) }}>
              <button
                type="button"
                onClick={() => pick(j)}
                aria-current={j === sel ? 'true' : undefined}
                className={`w-full rounded-md border border-border p-2 text-left text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${j === sel ? 'outline outline-2 outline-ring' : ''}`}
              >
                <span className={`mr-1 rounded px-1.5 py-px ${KIND[it.kind].chip}`}>{KIND[it.kind].letter} {KIND[it.kind].name}</span>
                {it.page != null && <span className="text-muted-foreground">p.{it.page}</span>}
                <span className={`mt-1 block ${j === sel ? '' : 'line-clamp-2'}`}>{it.text}</span>
              </button>
              {j === sel && it.kind === 'evidence' && verdict && (
                <div className="mt-1 rounded-md bg-muted p-2 text-xs">
                  {verdict.ai && <span className="mr-1 rounded bg-purple-100 px-1.5 py-px text-purple-900">AI</span>}
                  <b>{verdict.text}</b>
                  {verdict.quote && <p className="mt-1"><span className="italic">“{verdict.quote}”</span>{verdict.page != null && <span className="text-muted-foreground"> p. {verdict.page}</span>}</p>}
                  {verdict.reason && <p className="mt-1 text-muted-foreground">{verdict.reason}</p>}
                </div>
              )}
              {j === sel && (
                <button type="button" onClick={() => onInsert(it)} className={`${btn} mt-1`}>{insertLabel(it)}</button>
              )}
            </li>
          ))}
        </ul>
      </div>
      <p role="status" aria-live="polite" className="sr-only">{announce(items, sel)}</p>
    </div>
  )
}
