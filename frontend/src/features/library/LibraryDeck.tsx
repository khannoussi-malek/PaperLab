import { useEffect, useMemo, useRef, useState, type MutableRefObject } from 'react'
import type { Paper } from '@/api/client'
import { useNoteCounts, useNotes } from '@/api/queries'
import { TabSkeleton } from '@/features/workspaces/TabStates'
import { noteHref, readerHref } from '@/lib/route'
import { bookItems, toDeckPaper, type DeckPaper } from '../manuscripts/deck/deckModel'
import type { DeckAction } from '../manuscripts/deck/deckGestures'
import { DeckHands, HANDS_HELP } from '../manuscripts/deck/DeckHands'
import { PaperBook } from '../manuscripts/deck/PaperBook'
import { PaperDeck } from '../manuscripts/deck/PaperDeck'

type BookControls = { step: (by: 1 | -1) => void; selectId: (id: string) => void }

const openReader = (href: string) => window.open(href, '_blank', 'noopener')

function OpenBook({ paper, controls, onClose }: { paper: DeckPaper; controls: MutableRefObject<BookControls | null>; onClose: () => void }) {
  const notes = useNotes(paper.paper_id)
  const items = useMemo(() => bookItems(notes.data ?? [], paper.paper_id), [notes.data, paper.paper_id])
  const [selected, setSelected] = useState(0)
  useEffect(() => {
    controls.current = {
      step: (by) => setSelected((i) => Math.min(Math.max(i + by, 0), Math.max(items.length - 1, 0))),
      selectId: (id) => { const i = items.findIndex((it) => it.id === id); if (i >= 0) setSelected(i) },
    }
    return () => { controls.current = null }
  }, [controls, items])

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
        onOpenReader={(item) => openReader(item ? noteHref(paper.paper_id, item.noteId) : readerHref(paper.paper_id))}
        onClose={onClose}
      />
    </>
  )
}

/** The papers the list shows, as a deck, in the list's order. Open one to read its notes; nothing here inserts or deletes. */
export function LibraryDeck({ papers }: { papers: Paper[] }) {
  const counts = useNoteCounts(useMemo(() => papers.map((p) => p.id), [papers]))
  const deckPapers = useMemo(() => papers.map((p) => toDeckPaper(p, counts.data?.[p.id])), [papers, counts.data])
  const [currentId, setCurrentId] = useState<string | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const [hands, setHands] = useState(false) // off until asked: it turns the camera on
  const column = useRef<HTMLDivElement>(null)
  const book = useRef<BookControls | null>(null)
  const refocus = useRef(false)
  const closeBook = () => { refocus.current = true; setOpenId(null) }
  useEffect(() => {
    if (openId || !refocus.current) return
    refocus.current = false
    column.current?.querySelector<HTMLElement>('[aria-roledescription="paper deck"]')?.focus()
  }, [openId])

  const shown = deckPapers // exactly what the list shows; its toolbar is the only search
  const at = Math.max(0, shown.findIndex((p) => p.paper_id === currentId)) // by id, so a reorder never moves you off your paper
  const open = deckPapers.find((p) => p.paper_id === openId) ?? null

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
    if (id === shown[at]?.paper_id) setOpenId(id)
    else setCurrentId(id)
  }

  return (
    <div ref={column} className="relative">
      <div className="mb-1 flex items-center justify-end gap-2">
        {hands && <span className="text-[11px] text-muted-foreground">{HANDS_HELP}</span>}
        <button type="button" aria-pressed={hands} onClick={() => setHands((h) => !h)} className="rounded-md border border-border px-2 py-0.5 text-xs aria-pressed:bg-primary aria-pressed:text-primary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Hands</button>
      </div>
      {open ? (
        <OpenBook key={open.paper_id} paper={open} controls={book} onClose={closeBook} />
      ) : (
        <PaperDeck
          papers={shown}
          current={at}
          onCurrent={(i) => setCurrentId(shown[i]?.paper_id ?? null)}
          onOpen={(i) => { setCurrentId(shown[i].paper_id); setOpenId(shown[i].paper_id) }}
          label="Papers"
        />
      )}
      {hands && <DeckHands column={column} onAction={onHands} onSelect={onHold} onHidden={() => setHands(false)} typingPause={false} />}
    </div>
  )
}
