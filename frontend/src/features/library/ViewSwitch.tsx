import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { browserStorage } from '@/features/notes/highlightColors'
import { closeSession } from '@/features/triage/sessionId'

export type PaperView = 'list' | 'deck' | 'triage'
const VIEWS: readonly PaperView[] = ['list', 'deck', 'triage']
const LABELS: Record<PaperView, string> = { list: 'List', deck: 'Deck', triage: 'Triage' }

/**
 * The page's view, remembered under `key`; storage that fails or holds junk falls back to the list. Leaving triage ends
 * the `triageScope` session. `exitTriage` goes back to the list and returns focus to the Triage switch button.
 */
export function usePaperView(key: string, triageScope?: string): [PaperView, (view: PaperView) => void, () => void] {
  const [view, setView] = useState<PaperView>(() => {
    try {
      const stored = browserStorage()?.getItem(key)
      return VIEWS.find((v) => v === stored) ?? 'list'
    } catch {
      return 'list'
    }
  })
  function choose(next: PaperView) {
    if (view === 'triage' && next !== 'triage' && triageScope) closeSession(triageScope)
    setView(next)
    try {
      browserStorage()?.setItem(key, next)
    } catch {
      // ponytail: an unwritable store only means the choice is forgotten on reload
    }
  }
  function exitTriage() {
    choose('list')
    queueMicrotask(() => document.querySelector<HTMLElement>('[data-view-switch="triage"]')?.focus())
  }
  return [view, choose, exitTriage]
}

export function ViewSwitch({ view, onChange }: { view: PaperView; onChange: (view: PaperView) => void }) {
  return (
    <div role="group" aria-label="Show papers as" className="flex gap-1">
      {VIEWS.map((v) => (
        <Button key={v} data-view-switch={v} size="sm" variant={view === v ? 'secondary' : 'ghost'} aria-pressed={view === v} onClick={() => onChange(v)}>
          {LABELS[v]}
        </Button>
      ))}
    </div>
  )
}
