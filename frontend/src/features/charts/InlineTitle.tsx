import { useEffect, useState } from 'react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

type Tag = 'h1' | 'span'

type Props = {
  value: string
  label: string
  /** Saves the trimmed title. A thrown error's message shows under the field and keeps it open. */
  onSave: (title: string) => Promise<boolean>
  as?: Tag
  /** Uncontrolled (a click/double-click starts it) unless given, so a menu's Rename can start it from outside too. */
  editing?: boolean
  onEditingChange?: (editing: boolean) => void
}

const textClass: Record<Tag, string> = {
  h1: 'mt-1 truncate font-heading text-3xl font-semibold',
  span: 'truncate font-heading text-lg font-semibold',
}
const inputClass: Record<Tag, string> = {
  h1: 'mt-1 h-auto border-0 bg-transparent px-0 font-heading text-3xl font-semibold shadow-none focus-visible:ring-2',
  span: 'h-7 font-heading text-lg font-semibold',
}

/**
 * A renameable title, like `DatasetPage`'s `h1`: click (here, double-click, so a single click can still select the
 * text) or Enter to start, Enter saves (trimmed; blank cancels), Escape cancels. `editing`/`onEditingChange` let a
 * menu's Rename item start and stop it from outside too.
 */
export function InlineTitle({ value, label, onSave, as = 'span', editing: editingProp, onEditingChange }: Props) {
  const [internalEditing, setInternalEditing] = useState(false)
  const editing = editingProp ?? internalEditing
  const setEditing = onEditingChange ?? setInternalEditing

  const [draft, setDraft] = useState(value)
  const [error, setError] = useState<string | null>(null)

  // A fresh draft and no stale error each time editing starts.
  useEffect(() => {
    if (editing) {
      setDraft(value)
      setError(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing])

  async function commit() {
    const trimmed = draft.trim()
    if (!trimmed || trimmed === value) {
      setEditing(false)
      return
    }
    try {
      const saved = await onSave(trimmed)
      if (saved) setEditing(false)
      else setError("Couldn't save.")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save.")
    }
  }

  if (!editing) {
    const Element = as
    return (
      <Element
        tabIndex={0}
        title="Rename"
        onDoubleClick={() => setEditing(true)}
        onKeyDown={(e) => e.key === 'Enter' && setEditing(true)}
        className={cn(
          'cursor-text rounded-md focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none',
          textClass[as],
        )}
      >
        {value}
      </Element>
    )
  }

  return (
    <div className="flex flex-col gap-1">
      <Input
        autoFocus
        aria-label={label}
        aria-invalid={error ? true : undefined}
        value={draft}
        onChange={(e) => {
          setDraft(e.target.value)
          setError(null)
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') e.currentTarget.blur()
          else if (e.key === 'Escape') {
            setDraft(value)
            setEditing(false)
          }
        }}
        onBlur={() => void commit()}
        className={inputClass[as]}
      />
      {error && (
        <p role="alert" className="px-1 text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}
