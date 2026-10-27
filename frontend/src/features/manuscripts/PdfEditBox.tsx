import { useLayoutEffect, useRef, useState, type KeyboardEvent } from 'react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

const MARGIN = 8
type Props = {
  anchor: DOMRect
  initial: string
  /** Shown instead of the editor (text LaTeX made); only Open in source is offered. */
  notice?: string
  /** Rejects with a message the box shows; the box stays open. */
  onSave: (text: string) => Promise<void>
  onCancel: () => void
  onOpenSource: () => void
}

/** A small editor anchored at a spot of the PDF pane (its nearest positioned parent), clamped to stay visible. */
export function PdfEditBox({ anchor, initial, notice, onSave, onCancel, onOpenSource }: Props) {
  const root = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ left: MARGIN, top: MARGIN })
  const [text, setText] = useState(initial)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useLayoutEffect(() => {
    const me = root.current
    const pane = me?.offsetParent?.getBoundingClientRect()
    if (!me || !pane) return
    const clamp = (v: number, max: number) => Math.max(MARGIN, Math.min(v, max))
    setPos({ left: clamp(anchor.left - pane.left, pane.width - me.offsetWidth - MARGIN), top: clamp(anchor.bottom - pane.top + 4, pane.height - me.offsetHeight - MARGIN) })
  }, [anchor])

  const toPdf = () => root.current?.parentElement?.querySelector<HTMLElement>('[aria-label="PDF pages"]')?.focus()
  const cancel = () => { toPdf(); onCancel() }
  const save = async () => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await onSave(text)
      toPdf()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong. Please try again.')
    } finally {
      setBusy(false)
    }
  }
  const key = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Escape') { e.preventDefault(); cancel() }
    else if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void save() }
  }

  return (
    <div ref={root} role="dialog" aria-label="Edit from the PDF" style={pos} className="absolute z-10 flex w-72 max-w-[calc(100%-1rem)] flex-col gap-2 rounded-lg border border-glass-border bg-popover p-3 text-popover-foreground shadow-lg">
      {notice ? (
        <p className="text-sm">{notice}</p>
      ) : (
        <Textarea aria-label="Edit this text" autoFocus rows={4} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={key} className="font-mono text-xs" />
      )}
      {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
      <div className="flex items-center gap-2">
        <Button variant="link" size="sm" className="px-0" onClick={onOpenSource}>Open in source</Button>
        <span className="flex-1" />
        <Button variant="outline" size="sm" onClick={cancel}>Cancel</Button>
        {!notice && <Button size="sm" disabled={busy} onClick={() => void save()}>Save</Button>}
      </div>
    </div>
  )
}
