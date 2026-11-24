import { useEffect, useState } from 'react'

/** The command palette (Cmd/Ctrl+K) and the section dialogs it can open. */
export function useStudioCommands() {
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [sectionAsk, setSectionAsk] = useState<{ kind: 'new' | 'split'; n: number } | null>(null)
  useEffect(() => { // Cmd/Ctrl+K anywhere in the studio; CodeMirror leaves it alone, so it bubbles up from the editor too
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== 'k' || !(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey || e.defaultPrevented) return
      if (document.querySelector('[role=dialog][data-state=open]')) return // History, Move, Delete or the palette itself
      e.preventDefault()
      setPaletteOpen(true)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])
  const ask = (kind: 'new' | 'split') => setSectionAsk((a) => ({ kind, n: (a?.n ?? 0) + 1 }))
  return { paletteOpen, setPaletteOpen, sectionAsk, ask }
}
