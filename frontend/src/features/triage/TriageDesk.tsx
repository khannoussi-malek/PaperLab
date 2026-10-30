import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { Paper } from '@/api/client'
import { prefetchPaperSections } from '@/features/lenses/queries'
import { browserStorage } from '@/features/notes/highlightColors'
import { paperLabel } from '@/features/library/paperMeta'
import { useReducedMotion } from '@/features/manuscripts/deck/useReducedMotion'
import * as say from './announce'
import { CardClock } from './cardClock'
import { DeskStage } from './DeskStage'
import { PILES, REASONS, type Pile } from './piles'
import { ReasonChips } from './ReasonChips'
import { ShortcutHelp } from './ShortcutHelp'
import { TriageBar } from './TriageBar'
import { DeskStatus, TriageControls } from './TriageControls'
import { TriageDone } from './TriageDone'
import { TriageEmpty } from './TriageEmpty'
import { deskLayout, useDeskWidth } from './layout'
import { countsByPile, newSince, ORDERS, progress, type Order } from './queue'
import { closeSession } from './sessionId'
import { useDeskKeys } from './useDeskKeys'
import { useTriageSession } from './useTriageSession'

const DEFAULT_ORDER: Order = 'oldest'
const orderKey = (scope: string) => `paperlab-triage-order:${scope}`

function storedOrder(scope: string): Order {
  try {
    const v = browserStorage()?.getItem(orderKey(scope))
    return ORDERS.some((o) => o.value === v) ? (v as Order) : DEFAULT_ORDER
  } catch {
    return DEFAULT_ORDER
  }
}

type Props = {
  /** The list's filtered papers: they build (and re-freeze) the stack. */
  papers: Paper[]
  /** Every paper loaded for this scope, unfiltered. */
  library: Paper[]
  libraryReady?: boolean
  scope: string
  sourceLabel: string
  filterKey: string
  workspaceId?: string
  onExit: () => void
  onShowKept: () => void
  /** The `P` key: Task 8's PDF column toggles here. */
  onTogglePdf?: () => void
}

/** The triage desk: stage, controls, reason chips, the one key handler and the done screen. */
export function TriageDesk({ papers, library, libraryReady = true, scope, sourceLabel, filterKey, onExit, onShowKept, onTogglePdf }: Props) {
  const root = useRef<HTMLElement>(null)
  const layout = deskLayout(useDeskWidth(root))
  const reduced = useReducedMotion()
  const [includeDecided, setInclude] = useState(false)
  // The chips belong to the card they opened on: another top card (an undo, a failed save) closes them.
  const [reasonsFor, setReasonsFor] = useState<string | null>(null)
  const [held, setHeld] = useState<Pile | null>(null)
  const [helpOpen, setHelpOpen] = useState(false)
  const [departing, setDeparting] = useState<{ pile: Pile; paper: Paper } | null>(null)
  const [clock] = useState(() => new CardClock())
  const session = useTriageSession({
    scope, queueFrom: papers, library, libraryReady, filterKey, order: storedOrder(scope), includeDecided: false,
  })
  const { state, top, notReady } = session
  useEffect(() => root.current?.focus(), [])
  const topId = top?.id
  useEffect(() => clock.reset(), [topId, clock])
  const reasons = reasonsFor !== null && reasonsFor === topId
  const setReasons = (on: boolean) => setReasonsFor(on ? (topId ?? null) : null)
  const client = useQueryClient()
  const nextTwo = state.unseen.slice(1, 3).filter((id) => library.find((p) => p.id === id)?.has_pdf).join(',')
  useEffect(() => {
    for (const id of nextTwo.split(',').filter(Boolean)) void prefetchPaperSections(client, id)
  }, [client, nextTwo])

  const exit = () => {
    closeSession(scope)
    onExit()
  }
  const toggleInclude = (on: boolean) => {
    setInclude(on)
    session.setIncludeDecided(on)
  }
  const changeOrder = (order: Order) => {
    try {
      browserStorage()?.setItem(orderKey(scope), order)
    } catch {
      // ponytail: an unwritable store only means the order is forgotten on reload
    }
    session.setOrder(order)
  }
  const focusRoot = () => root.current?.focus()
  const go = (pile: Pile, reason?: string, note?: string) => {
    if (!top) return
    setReasons(false)
    setHeld(null) // the stamp belongs to the card the key acted on, not the next one
    setDeparting({ pile, paper: top })
    session.decide(pile, { reason, note, clock: clock.read() })
    focusRoot()
  }
  // Not relevant always asks why first: nothing is sent until a chip commits.
  const choose = (pile: Pile) => {
    if (!top) return
    if (pile !== 'not_relevant') return go(pile)
    setReasons(true)
    focusRoot()
  }
  const cancelReason = () => { setReasons(false); focusRoot() }
  const undo = () => {
    setReasons(false)
    session.undo()
    focusRoot()
  }
  useDeskKeys(root, {
    reasonsShowing: reasons,
    helpOpen,
    onPile: choose,
    onHold: setHeld,
    onReason: (n) => root.current?.querySelectorAll<HTMLElement>('[data-reason-chip]')[n - 1]?.click(),
    cancelReason,
    closeHelp: () => setHelpOpen(false),
    exit,
    undo,
    togglePdf: () => onTogglePdf?.(),
    openHelp: () => setHelpOpen(true),
    focusAbstract: () => root.current?.querySelector<HTMLElement>('[aria-label="Abstract"]')?.focus(),
  })

  // A done-screen button unmounts with its action: the keys must keep working, so focus goes to the desk.
  const keepFocus = (f: () => void) => () => { f(); focusRoot() }
  const startOver = () => { setReasons(false); setDeparting(null); session.startOver() }

  const last = state.done.at(-1)
  const lastPaper = last && library.find((p) => p.id === last.id)
  const undoInfo = last ? { label: lastPaper ? `${PILES[last.pile].label} '${paperLabel(lastPaper)}'` : PILES[last.pile].label, count: state.done.length } : null
  const finished = state.unseen.length === 0 && (state.total > 0 || state.done.length > 0)
  const empty = state.total === 0 && state.done.length === 0
  return (
    <section
      ref={root}
      role="group"
      aria-roledescription="triage desk"
      aria-label="Triage"
      tabIndex={0}
      data-layout={layout}
      className="flex flex-col gap-3 rounded-xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      <TriageBar
        sourceLabel={sourceLabel}
        left={state.unseen.length}
        total={state.total}
        notReady={notReady}
        order={state.order}
        includeDecided={includeDecided}
        onOrder={changeOrder}
        onIncludeDecided={toggleInclude}
        onExit={exit}
        onStartOver={empty || finished ? undefined : keepFocus(startOver)}
        canStartOver={session.canStartOver}
      />
      <ShortcutHelp open={helpOpen} onOpenChange={setHelpOpen} />
      <DeskStatus announcement={reasons ? say.reasonRow() : session.announcement} alert={session.alert} />
      {empty ? (
        <TriageEmpty canInclude={!includeDecided} onInclude={() => toggleInclude(true)} onBack={exit} />
      ) : finished ? (
        <TriageDone
          sessionId={session.sessionId}
          skipped={state.skipped.length}
          canReviewSkipped={session.canReviewSkipped}
          canStartOver={session.canStartOver}
          newSince={newSince(state, papers, { includeDecided })}
          undo={undoInfo}
          onUndo={undo}
          onReviewSkipped={keepFocus(session.reviewSkipped)}
          onShowKept={keepFocus(onShowKept)}
          onAddNew={keepFocus(session.addNew)}
          onStartOver={keepFocus(startOver)}
          onBack={exit}
        />
      ) : top ? (
        <>
          <div data-triage-region tabIndex={-1} className="outline-none">
            <DeskStage
              top={top}
              behind={state.unseen.slice(1, 3).flatMap((id) => library.find((p) => p.id === id) ?? [])}
              counts={countsByPile(state)}
              layout={layout}
              hot={held ?? (reasons ? 'not_relevant' : null)}
              hovering={reasons ? 'not_relevant' : null}
              departing={departing}
              onCommit={choose}
              onHover={() => {}}
              reduced={reduced}
            />
          </div>
          {reasons && <ReasonChips reasons={REASONS.not_relevant} noteFor="other" onPick={(r, note) => go('not_relevant', r, note)} onCancel={cancelReason} />}
          <TriageControls layout={layout} undo={undoInfo} onUndo={undo} onDecide={choose} progress={progress(state)} />
        </>
      ) : (
        <p className="text-muted-foreground">Getting the next paper ready…</p>
      )}
    </section>
  )
}
