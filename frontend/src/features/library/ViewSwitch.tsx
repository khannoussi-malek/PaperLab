import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { browserStorage } from '@/features/notes/highlightColors'

export type PaperView = 'list' | 'deck'

/** The page's view, remembered under `key`; storage that fails or holds junk falls back to the list. */
export function usePaperView(key: string): [PaperView, (view: PaperView) => void] {
  const [view, setView] = useState<PaperView>(() => {
    try {
      return browserStorage()?.getItem(key) === 'deck' ? 'deck' : 'list'
    } catch {
      return 'list'
    }
  })
  function choose(next: PaperView) {
    setView(next)
    try {
      browserStorage()?.setItem(key, next)
    } catch {
      // ponytail: an unwritable store only means the choice is forgotten on reload
    }
  }
  return [view, choose]
}

export function ViewSwitch({ view, onChange }: { view: PaperView; onChange: (view: PaperView) => void }) {
  return (
    <div role="group" aria-label="View" className="flex gap-1">
      {(['list', 'deck'] as const).map((v) => (
        <Button key={v} size="sm" variant={view === v ? 'secondary' : 'ghost'} aria-pressed={view === v} onClick={() => onChange(v)}>
          {v === 'list' ? 'List' : 'Deck'}
        </Button>
      ))}
    </div>
  )
}
