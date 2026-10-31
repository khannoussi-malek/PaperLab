import type { KeyboardEvent } from 'react'
import { cn } from '@/lib/utils'

export type DeskTab = 'paper' | 'pdf'
const TABS: { id: DeskTab; label: string }[] = [{ id: 'paper', label: 'Paper' }, { id: 'pdf', label: 'PDF' }]

/** Paper | PDF for the middle widths. Arrows act only while a tab has focus: on the desk they are piles. */
export function PdfTabs({ tab, onTab }: { tab: DeskTab; onTab: (t: DeskTab) => void }) {
  const keys = (e: KeyboardEvent) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
    e.stopPropagation()
    e.preventDefault()
    onTab(tab === 'paper' ? 'pdf' : 'paper') // two tabs: either arrow reaches the other one
    // the newly selected tab takes focus so the next arrow keeps working
    queueMicrotask(() => document.getElementById(`triage-tab-${tab === 'paper' ? 'pdf' : 'paper'}`)?.focus())
  }
  return (
    <div role="tablist" aria-label="Paper or PDF" className="flex gap-1 border-b border-border">
      {TABS.map((t) => (
        <button
          key={t.id}
          id={`triage-tab-${t.id}`}
          role="tab"
          type="button"
          aria-selected={tab === t.id}
          aria-controls={`triage-panel-${t.id}`}
          tabIndex={tab === t.id ? 0 : -1}
          onKeyDown={keys}
          onClick={() => onTab(t.id)}
          className={cn('-mb-px border-b-2 px-3 py-1.5 text-sm font-medium outline-none focus-visible:ring-3 focus-visible:ring-ring/50', tab === t.id ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground')}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}
