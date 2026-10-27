import { useEffect, useMemo, useRef, useState, type MutableRefObject } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, ApiError, type EvidenceFound, type EvidenceRow } from '@/api/client'
import { useManuscriptPapers, useNotes, usePinPaper } from '@/api/queries'
import { TabSkeleton } from '@/features/workspaces/TabStates'
import { chunkHref, noteHref, readerHref } from '@/lib/route'
import { manuscriptFailure } from '../errors'
import { sentenceAtCursor } from '../evidence/claimText'
import { bookItems, citedKeys, deckOrder, evidenceFirst, evidenceItems, insertText, NO_MODEL, verdictView, type BookItem, type DeckPaper, type VerdictView } from './deckModel'
import { PaperBook } from './PaperBook'
import { DeckHands, HANDS_HELP } from './DeckHands'
import type { DeckAction } from './deckGestures'
import { PaperDeck } from './PaperDeck'

const RANK_DELAY_MS = 500
const RANK_MAX_CHARS = 20_000 // RankIn's max_length: more is a 422
const EVIDENCE_POLL_MS = 2000

const EVIDENCE_ERRORS: Record<string, string> = {
  no_workspace: "This manuscript isn't in a workspace, so there are no papers to search.",
  empty_claim: 'Put the cursor in a sentence first.',
  claim_too_long: "That's too long to check. Select one sentence.",
}
const evidenceError = (e: unknown) =>
  (e instanceof ApiError && EVIDENCE_ERRORS[e.code]) || (e instanceof Error ? e.message : 'Something went wrong. Please try again.')

const NONE: EvidenceFound['papers'][number]['passages'] = []
type Evidence = { sentence: string; found: EvidenceFound }

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
  /** Mod+E in the editor: find evidence for the selection, or the sentence at the cursor. A new `n` asks again. */
  evidenceAsk?: { doc: string; from: number; to: number; n: number } | null
  /** The deck's Find evidence button and Mod+E: run it on the editor's last cursor. False when there is none yet. */
  onFindEvidence?: () => boolean
}

/** What the hands can do to an open book: move between its items, or turn to one by id. */
type BookControls = { step: (by: 1 | -1) => void; selectId: (id: string) => void }

const openReader = (href: string) => window.open(href, '_blank', 'noopener')

function OpenBook({ manuscriptId, paper, onInsert, onClose, onNotice, controls, passages, verdict }: { passages: EvidenceFound['papers'][number]['passages']; verdict: VerdictView | null; controls: MutableRefObject<BookControls | null>; manuscriptId: string; paper: DeckPaper; onInsert: DeckColumnProps['onInsert']; onClose: () => void; onNotice: (s: string | null) => void }) {
  const notes = useNotes(paper.paper_id)
  const pin = usePinPaper()
  const items = useMemo(() => [...evidenceItems(passages), ...bookItems(notes.data ?? [], paper.paper_id)], [notes.data, paper.paper_id, passages])
  const [selected, setSelected] = useState(0)
  useEffect(() => setSelected(0), [passages]) // new passages: never point silently at a different item
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
        onOpenReader={(item) => openReader(!item ? readerHref(paper.paper_id) : item.chunkId ? chunkHref(paper.paper_id, item.chunkId, item.page ?? 1) : noteHref(paper.paper_id, item.noteId))}
        verdict={verdict}
        onClose={onClose}
      />
    </>
  )
}

/** The Papers column: the workspace's papers as a deck, ordered for the section being written; open one to insert from it. */
export function DeckColumn({ manuscriptId, sectionKey, sectionText, allTexts, onInsert, openKey, evidenceAsk, onFindEvidence }: DeckColumnProps) {
  const papers = useManuscriptPapers(manuscriptId)
  const [filter, setFilter] = useState('')
  const [currentId, setCurrentId] = useState<string | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const [ranked, setRanked] = useState<string[]>([])
  const [notice, setNotice] = useState<string | null>(null)
  const [evidence, setEvidence] = useState<Evidence | null>(null)
  const [evidenceMsg, setEvidenceMsg] = useState<string | null>(null) // an error, or "Finding evidence…"
  const [finding, setFinding] = useState(false)
  const handledAsk = useRef(0)
  const lastAsk = useRef(0) // the newest ask; an older answer arriving late is dropped. 0 once unmounted.
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
      api.rankPapers(manuscriptId, text.current.slice(0, RANK_MAX_CHARS)).then((r) => live && setRanked(r.paper_ids), () => {})
    }, RANK_DELAY_MS)
    return () => { live = false; clearTimeout(timer) }
  }, [manuscriptId, sectionKey])

  const clearEvidence = () => { lastAsk.current += 1; setEvidence(null); setEvidenceMsg(null); setFinding(false) }
  useEffect(() => () => { lastAsk.current = -1 }, [])
  useEffect(() => {
    if (!evidenceAsk || evidenceAsk.n === handledAsk.current) return
    handledAsk.current = evidenceAsk.n
    const ask = ++lastAsk.current
    setEvidence(null) // the old check stops polling now
    const sentence = sentenceAtCursor(evidenceAsk.doc, evidenceAsk.from, evidenceAsk.to)
    if (!sentence) return setEvidenceMsg(EVIDENCE_ERRORS.empty_claim), setFinding(false)
    setEvidenceMsg(null)
    setFinding(true)
    api.findEvidence(manuscriptId, sentence.plain).then(
      (found) => { if (lastAsk.current === ask) { setEvidence({ sentence: sentence.plain, found }); setFinding(false) } },
      (e) => { if (lastAsk.current === ask) { setEvidenceMsg(evidenceError(e)); setFinding(false) } },
    )
  }, [evidenceAsk, manuscriptId])

  const hash = evidence?.found.sentence_hash
  const unavailable = evidence?.found.verdicts === 'unavailable'
  const rows = useQuery({
    queryKey: ['manuscriptEvidence', manuscriptId, hash],
    queryFn: () => api.evidenceRows(manuscriptId, hash!),
    enabled: !!hash && !unavailable,
    gcTime: 0,
    refetchInterval: (q) => {
      if (q.state.status === 'error') return false
      const d = q.state.data as EvidenceRow[] | undefined
      return !d || d.some((r) => r.status === 'queued' || r.status === 'running') ? EVIDENCE_POLL_MS : false
    },
  })
  const findFromDeck = () => {
    if (!onFindEvidence) return
    if (onFindEvidence()) return
    clearEvidence()
    setEvidenceMsg(EVIDENCE_ERRORS.empty_claim)
  }
  const evidenceById = useMemo(() => {
    const byPaper = new Map(rows.data?.map((r) => [r.paper_id, r]))
    return new Map((evidence?.found.papers ?? []).map((p) => [p.paper_id, { count: p.passages.length, passages: p.passages, verdict: verdictView(byPaper.get(p.paper_id), unavailable) }]))
  }, [evidence, rows.data, unavailable])

  const inSection = useMemo(() => citedKeys([sectionText]), [sectionText])
  const elsewhere = useMemo(() => citedKeys(allTexts), [allTexts.join('\u0000')]) // eslint-disable-line react-hooks/exhaustive-deps
  const ordered = useMemo(
    () => evidenceFirst(deckOrder(papers.data ?? [], inSection, elsewhere, ranked), evidence?.found.papers.map((p) => p.paper_id) ?? []),
    [papers.data, inSection, elsewhere, ranked, evidence],
  )
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
    <div ref={column} className="relative h-full" onKeyDown={(e) => { if (e.key.toLowerCase() === 'e' && (e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && onFindEvidence) { e.preventDefault(); findFromDeck(); return } if (e.key === 'Escape' && !open && (evidence || evidenceMsg || finding)) { clearEvidence(); e.preventDefault() } }}>
    <div className="h-full overflow-auto p-2">
      <div className="mb-1 flex items-center justify-end gap-2">
        {hands && <span className="text-[11px] text-muted-foreground">{HANDS_HELP}</span>}
        {onFindEvidence && <button type="button" onClick={findFromDeck} className="rounded-md border border-blue-300 px-2 py-0.5 text-xs text-blue-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring dark:border-blue-800 dark:text-blue-100">Find evidence</button>}
        <button type="button" aria-pressed={hands} onClick={() => setHands((h) => !h)} className="rounded-md border border-border px-2 py-0.5 text-xs aria-pressed:bg-primary aria-pressed:text-primary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Hands</button>
      </div>
      {(evidence || evidenceMsg || finding) && (
        <div className="mb-2 rounded-md border border-blue-300 bg-blue-50 p-2 text-xs text-blue-950 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-100">
          <div className="flex items-start justify-between gap-2">
            <span className="line-clamp-3">{evidence ? <>Evidence for: ‘{evidence.sentence}’</> : finding ? 'Finding evidence…' : 'Evidence'}</span>
            <button type="button" onClick={clearEvidence} className="shrink-0 rounded-md border border-blue-300 px-2 py-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Clear</button>
          </div>
          {evidenceMsg && <p role="alert" className="mt-1">{evidenceMsg}</p>}
          {evidence && !evidence.found.papers.length && <p className="mt-1">No passages found in this workspace's papers.</p>}
          {rows.isError && (
            <p role="alert" className="mt-1 flex items-center gap-2">Couldn't load the verdicts.
              <button type="button" onClick={() => void rows.refetch()} className="rounded-md border border-blue-300 px-2 py-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Retry</button>
            </p>
          )}
          {unavailable && evidence.found.papers.length > 0 && <p className="mt-1">{NO_MODEL}</p>}
        </div>
      )}
      {notice && <p role="status" className="mb-2 rounded-md border border-border bg-muted px-2 py-1 text-xs">{notice}</p>}
      {open ? (
        <OpenBook key={open.paper_id} manuscriptId={manuscriptId} paper={open} onInsert={onInsert} onClose={closeBook} onNotice={setNotice} controls={book} passages={evidenceById.get(open.paper_id)?.passages ?? NONE} verdict={evidenceById.get(open.paper_id)?.verdict ?? null} />
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
          evidence={evidenceById}
        />
      )}
    </div>
    {hands && <DeckHands column={column} onAction={onHands} onSelect={onHold} onHidden={() => setHands(false)} />}
    </div>
  )
}
