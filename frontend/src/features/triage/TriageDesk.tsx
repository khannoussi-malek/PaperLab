import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import type { Paper } from '@/api/client'
import { browserStorage } from '@/features/notes/highlightColors'
import { TriageBar } from './TriageBar'
import { TriageEmpty } from './TriageEmpty'
import { deskLayout, useDeskWidth } from './layout'
import { ORDERS, type Order } from './queue'
import { closeSession } from './sessionId'
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
}

/** The triage desk. Stage and controls are placeholders until the card, piles and keys land. */
export function TriageDesk({ papers, library, libraryReady = true, scope, sourceLabel, filterKey, onExit }: Props) {
  const root = useRef<HTMLElement>(null)
  const layout = deskLayout(useDeskWidth(root))
  const [includeDecided, setInclude] = useState(false)
  const session = useTriageSession({
    scope, queueFrom: papers, library, libraryReady, filterKey, order: storedOrder(scope), includeDecided: false,
  })
  const { state, top, notReady } = session
  useEffect(() => root.current?.focus(), [])

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
  // The one desk keydown listener: later keys extend this handler. Events from portalled popups (an open Select) are not ours.
  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    if (e.defaultPrevented || !e.currentTarget.contains(e.target as Node)) return
    if (e.key === 'Escape') exit()
  }

  const empty = state.total === 0 && state.done.length === 0
  return (
    <section
      ref={root}
      role="group"
      aria-roledescription="triage desk"
      aria-label="Triage"
      tabIndex={0}
      data-layout={layout}
      onKeyDown={onKeyDown}
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
      />
      <div role="status" aria-live="polite" className="sr-only">{session.announcement}</div>
      {empty ? (
        <TriageEmpty canInclude={!includeDecided} onInclude={() => toggleInclude(true)} onBack={exit} />
      ) : top ? (
        <article className="rounded-xl border border-glass-border p-6">
          <h2 className="font-heading text-xl font-semibold wrap-anywhere">{top.title}</h2>
        </article>
      ) : (
        <p className="text-muted-foreground">That is the whole stack for now.</p>
      )}
    </section>
  )
}
