import { Hash } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { NoteKind } from '@/api/client'
import { popIn } from '@/components/motion'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import type { NoteDraft } from '../reader/selection'
import { HighlightColorPicker } from './HighlightColorPicker'
import { KindSelect } from './KindSelect'
import { KIND_HINT, swapTemplate } from './noteKinds'

/** Body and kind together: a new kind swaps an untouched template, never typed text. */
function useKindBody(initialKind: NoteKind | null) {
  const [kind, setKind] = useState<NoteKind | null>(initialKind)
  const [body, setBody] = useState(() => swapTemplate('', null, initialKind))
  const pickKind = (next: NoteKind | null) => {
    setBody((b) => swapTemplate(b, kind, next))
    setKind(next)
  }
  // Write it can hand an open composer another kind: typed text stays, an untouched template swaps.
  useEffect(() => {
    pickKind(initialKind)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialKind])
  return { kind, body, setBody, pickKind }
}

function KindRow({ kind, onChange, fixed }: { kind: NoteKind | null; onChange: (k: NoteKind | null) => void; fixed?: boolean }) {
  return (
    <>
      {fixed ? <p className="text-sm font-medium">Figure</p> : <KindSelect value={kind} onChange={onChange} />}
      {kind && <p className="text-xs whitespace-pre-line text-muted-foreground">{KIND_HINT[kind]}</p>}
    </>
  )
}

type Props = {
  draft: NoteDraft
  color: string
  onColorChange: (hex: string) => void
  onSave: (body: string, kind: NoteKind | null) => Promise<boolean>
  onCancel: () => void
  onAddNumber: () => void
}

export function NoteComposer({ draft, color, onColorChange, onSave, onCancel, onAddNumber }: Props) {
  const { kind, body, setBody, pickKind } = useKindBody(draft.figure ? 'figure' : null)
  const [saving, setSaving] = useState(false)

  async function save() {
    setSaving(true)
    await onSave(body, kind)
    setSaving(false)
  }

  return (
    // A form, not an <article>: saved notes are the only articles in the panel.
    <form
      className={cn('origin-top', popIn)}
      onSubmit={(e) => {
        e.preventDefault()
        void save()
      }}
    >
      <Card size="sm" className="bg-glass-strong ring-2 ring-primary">
        <CardContent className="flex flex-col gap-2">
          <blockquote className="line-clamp-2 border-l-2 pl-2 text-muted-foreground" title={draft.quotedText}>
            {draft.quotedText}
          </blockquote>
          <Textarea
            autoFocus
            aria-label="Note"
            placeholder="Your note (optional). Ctrl/⌘+Enter saves."
            value={body}
            onChange={(e) => setBody(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault()
                void save()
              }
              if (e.key === 'Escape') onCancel()
            }}
          />
          <KindRow kind={kind} onChange={pickKind} fixed={draft.figure} />
          <HighlightColorPicker value={color} onChange={onColorChange} />
        </CardContent>
        <CardFooter className="justify-end gap-2">
          {/* A number is placed on a page; a quote from the abstract (no rects) has none. */}
          {draft.rects.length > 0 && !draft.figure && (
            <Button type="button" variant="ghost" size="sm" onClick={onAddNumber}>
              <Hash aria-hidden />
              Add as number
            </Button>
          )}
          <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit" size="sm" disabled={saving}>
            Save note
          </Button>
        </CardFooter>
      </Card>
    </form>
  )
}

/** A note on the whole paper, no quote or colour: also the only composer a paper without a PDF has. */
export function PlainNoteComposer({
  initialKind = null,
  onSave,
  onCancel,
  onDirtyChange,
}: {
  initialKind?: NoteKind | null
  onSave: (body: string, kind: NoteKind | null) => Promise<boolean>
  onCancel?: () => void
  /** Whether the body holds text the reader typed (not empty, not just the template). */
  onDirtyChange?: (dirty: boolean) => void
}) {
  const { kind, body, setBody, pickKind } = useKindBody(initialKind)
  const [saving, setSaving] = useState(false)
  const dirty = body.trim() !== '' && body !== swapTemplate('', null, kind)
  useEffect(() => {
    onDirtyChange?.(dirty)
    return () => onDirtyChange?.(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- report changes of `dirty` only
  }, [dirty])

  async function save() {
    if (!body.trim()) return
    setSaving(true)
    if (await onSave(body, kind)) setBody(swapTemplate('', null, kind))
    setSaving(false)
  }

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        void save()
      }}
    >
      <Textarea
        aria-label="New note"
        placeholder="Write a note. Ctrl/⌘+Enter saves."
        value={body}
        onChange={(e) => setBody(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
            e.preventDefault()
            void save()
          }
          if (e.key === 'Escape' && !dirty) onCancel?.() // typed text goes only on an explicit Cancel
        }}
      />
      <KindRow kind={kind} onChange={pickKind} />
      <div className="flex justify-end gap-2">
        {onCancel && (
          <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
        )}
        <Button type="submit" size="sm" disabled={saving || !body.trim()}>
          Save note
        </Button>
      </div>
    </form>
  )
}
