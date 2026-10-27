import { useEffect, useMemo, useRef, useState, type MutableRefObject } from 'react'
import { api } from '@/api/client'
import { useManuscriptPapers, useNotes, usePinPaper } from '@/api/queries'
import { TabSkeleton } from '@/features/workspaces/TabStates'
import { noteHref, readerHref } from '@/lib/route'
import { manuscriptFailure } from '../errors'
import { bookItems, citedKeys, deckOrder, insertText, type BookItem, type DeckPaper } from './deckModel'
import { PaperBook } from './PaperBook'
import { DeckHands, HANDS_HELP } from './DeckHands'
import type { DeckAction } from './deckGestures'
import { PaperDeck } from './PaperDeck'

const RANK_DELAY_MS = 500

export type DeckColumnProps = {
  manuscriptId: string
  /** Identifies the section being written; ranking runs once each time it changes. */
  sectionKey: string
  sectionText: string
  /** The live text of every .tex file (the section's own included). */
  allTexts: string[]
  /** Puts text into the editor; false when there is no open file to put it in. */
  onInsert: (text: string) => boolean
  /** Mod+Alt+K on a \cite key: open that paper, already open. A new `n` asks again. */
  openKey: { key: string; n: number } | null
}

/** What the hands can do to an open book: move between its items, or turn to one by id. */
type BookControls = { step: (by: 1 | -1) => void; selectId: (id: string) => void }

const openReader = (href: string) => window.open(href, '_blank', 'noopener')

function OpenBook({ manuscriptId, paper, onInsert, onClose, onNotice, controls }: { controls: MutableRefObject<BookControls | null>; manuscriptId: string; paper: DeckPaper; onInsert: DeckColumnProps['onInsert']; onClose: () => void; onNotice: (s: string | null) => void }) {
  const notes = useNotes(paper.paper_id)
  const pin = usePinPaper()
  const items = useMemo(() => bookItems(notes.data ?? [], paper.paper_id), [notes.data, paper.paper_id])
  const [selected, setSelected] = useState(0)
  useEffect(() => {
    controls.current = {
      step: (by) => setSelected((i) => Math.min(Math.max(i + by, 0), Math.max(items.length - 1, 0))),
      selectId: (id) => { const i = items.findIndex((it) => it.id === id); if (i >= 0) setSelected(i) },
    }
    return () => { controls.current = null }
  }, [controls, items])

  const insert = async (item: BookItem | null) => {
    onNotice(null)
    try {
      const pinned = await pin.mutateAsync({ id: manuscriptId, paperId: paper.paper_id }) // so the key is in the bibliography
      const text = insertText(item, typeof pinned?.key === 'string' ? pinned.key : paper.key)
      if (!onInsert(text)) onNotice('Open a file in the editor to insert there.')
    } catch (e) {
      onNotice(manuscriptFailure(e instanceof Error ? e : new Error(String(e))))
    }
  }

  if (notes.isPending) return <TabSkeleton label="Loading notes" />
  return (
    <>
      {notes.error && <p role="alert" className="mb-2 text-xs text-destructive">Couldn't load this paper's notes: {notes.error.message}</p>}
      <PaperBook
        key={paper.paper_id}
        paper={paper}
        items={items}
        selected={selected}
        onSelect={setSelected}
        onInsert={(item) => void insert(item)}
        onOpenReader={(item) => openReader(item ? noteHref(paper.paper_id, item.noteId) : readerHref(paper.paper_id))}
        onClose={onClose}
      />
    </>
  )
}

/** The Papers column: the workspace's papers as a deck, ordered for the section being written; open one to insert from it. */
export function DeckColumn({ manuscriptId, sectionKey, sectionText, allTexts, onInsert, openKey }: DeckColumnProps) {
  const papers = useManuscriptPapers(manuscriptId)
  const [filter, setFilter] = useState('')
  const [currentId, setCurrentId] = useState<string | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const [ranked, setRanked] = useState<string[]>([])
  const [notice, setNotice] = useState<string | null>(null)
  const [hands, setHands] = useState(false) // off until asked: it turns the camera on
  const column = useRef<HTMLDivElement>(null)
  const book = useRef<BookControls | null>(null)
  // Esc / Back to the deck: the book leaves the DOM, so focus goes back to the deck, never to <body>.
  // Not for a hand gesture: focus may be in the editor then.
  const refocus = useRef(false)
  const closeBook = () => { refocus.current = true; setOpenId(null) }
  useEffect(() => {
    if (openId || !refocus.current) return
    refocus.current = false
    column.current?.querySelector<HTMLElement>('[aria-roledescription="paper deck"]')?.focus()
  }, [openId])

  // Once per section opened (after a pause), never per keystroke; no ranking is fine, so a failure is silent.
  const text = useRef(sectionText)
  text.current = sectionText
  useEffect(() => {
    let live = true
    const timer = setTimeout(() => {
      if (!text.current.trim()) return setRanked([])
      api.rankPapers(manuscriptId, text.current).then((r) => live && setRanked(r.paper_ids), () => {})
    }, RANK_DELAY_MS)
    return () => { live = false; clearTimeout(timer) }
  }, [manuscriptId, sectionKey])

  const inSection = useMemo(() => citedKeys([sectionText]), [sectionText])
  const elsewhere = useMemo(() => citedKeys(allTexts), [allTexts.join('\u0000')]) // eslint-disable-line react-hooks/exhaustive-deps
  const ordered = useMemo(() => deckOrder(papers.data ?? [], inSection, elsewhere, ranked), [papers.data, inSection, elsewhere, ranked])
  const shown = useMemo(() => {
    const q = filter.trim().toLowerCase()
    return q ? ordered.filter((p) => [p.title, p.first_author, p.year].join(' ').toLowerCase().includes(q)) : ordered
  }, [ordered, filter])
  const at = Math.max(0, shown.findIndex((p) => p.paper_id === currentId)) // by id, so a reorder never changes the paper you are on
  const open = ordered.find((p) => p.paper_id === openId) ?? null

  const onHands = (a: DeckAction) => {
    if (a.type === 'step') {
      if (book.current) book.current.step(a.by)
      else if (shown.length) setCurrentId(shown[Math.min(Math.max(at + a.by, 0), shown.length - 1)].paper_id)
    } else if (a.type === 'open') {
      if (!open && shown[at]) { setCurrentId(shown[at].paper_id); setOpenId(shown[at].paper_id) }
    } else setOpenId(null)
  }
  const onHold = (id: string, kind: 'card' | 'tab') => {
    if (kind === 'tab') return book.current?.selectId(id)
    if (open) return
    if (id === shown[at]?.paper_id) setOpenId(id) // a second hold on the front card opens it
    else setCurrentId(id)
  }

  const handled = useRef(0)
  useEffect(() => {
    if (!openKey || openKey.n === handled.current || !papers.data) return
    handled.current = openKey.n
    const hit = papers.data.find((p) => p.key === openKey.key)
    if (!hit) return setNotice(`${openKey.key} isn't in this workspace's papers.`)
    setNotice(null)
    setFilter('')
    setCurrentId(hit.paper_id)
    setOpenId(hit.paper_id)
  }, [openKey, papers.data])

  if (papers.isPending) return <div className="px-2"><TabSkeleton label="Loading papers" /></div>
  if (papers.error) return <p role="alert" className="p-3 text-sm text-destructive">Couldn't load the papers: {papers.error.message}</p>

  const cited = new Set([...inSection, ...elsewhere])
  return (
    <div ref={column} className="relative h-full">
    <div className="h-full overflow-auto p-2">
      <div className="mb-1 flex items-center justify-end gap-2">
        {hands && <span className="text-[11px] text-muted-foreground">{HANDS_HELP}</span>}
        <button type="button" aria-pressed={hands} onClick={() => setHands((h) => !h)} className="rounded-md border border-border px-2 py-0.5 text-xs aria-pressed:bg-primary aria-pressed:text-primary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Hands</button>
      </div>
      {notice && <p role="status" className="mb-2 rounded-md border border-border bg-muted px-2 py-1 text-xs">{notice}</p>}
      {open ? (
        <OpenBook key={open.paper_id} manuscriptId={manuscriptId} paper={open} onInsert={onInsert} onClose={closeBook} onNotice={setNotice} controls={book} />
      ) : (
        <PaperDeck
          papers={shown}
          current={at}
          onCurrent={(i) => setCurrentId(shown[i]?.paper_id ?? null)}
          onOpen={(i) => { setCurrentId(shown[i].paper_id); setOpenId(shown[i].paper_id) }}
          filter={filter}
          onFilter={setFilter}
          label="Papers"
          cited={cited}
        />
      )}
    </div>
    {hands && <DeckHands column={column} onAction={onHands} onSelect={onHold} onHidden={() => setHands(false)} />}
    </div>
  )
}
