import { Check, ChartColumn, Copy } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { Note } from '@/api/client'
import { isFresh, slideUpIn } from '@/components/motion'
import { Button } from '@/components/ui/button'
import { copyText } from '@/lib/clipboard'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { AttachChartDialog } from './AttachChartDialog'
import { HighlightColorPicker } from './HighlightColorPicker'
import { NoteCharts } from './NoteCharts'
import { ProvenanceBadge } from './ProvenanceBadge'

type Props = {
  note: Note
  paperId: string
  active?: boolean
  /** The hover card's version: no quote or page link (the highlight is right there), and not an `article.note`. */
  compact?: boolean
  startEditing?: boolean
  onSelect?: () => void
  onUpdate: (body: string) => Promise<boolean>
  onColorChange: (hex: string) => Promise<boolean>
  onDelete: () => Promise<void>
  /** Told the note's id and whether it's editing, whenever editing starts or stops, and "stopped" on unmount. */
  onEditingChange?: (noteId: string, editing: boolean) => void
  className?: string
}

export function NoteCard({
  note,
  paperId,
  active = false,
  compact = false,
  startEditing = false,
  onSelect,
  onUpdate,
  onColorChange,
  onDelete,
  onEditingChange,
  className,
}: Props) {
  const [editing, setEditing] = useState(startEditing)
  const [body, setBody] = useState(note.body)
  const [attachingChart, setAttachingChart] = useState(false)
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState<string | null>(null)
  const anchor = note.anchors.find((a) => a.paper_id === paperId)

  useEffect(() => {
    onEditingChange?.(note.id, editing)
    return () => onEditingChange?.(note.id, false)
  }, [editing, note.id, onEditingChange])

  useEffect(() => {
    if (!copied) return
    const timer = setTimeout(() => setCopied(false), 1500)
    return () => clearTimeout(timer)
  }, [copied])

  async function copyQuote(quote: string) {
    try {
      await copyText(quote)
      setCopyError(null)
      setCopied(true)
    } catch (error) {
      setCopied(false)
      setCopyError(error instanceof Error ? error.message : 'Could not copy.')
    }
  }

  async function save() {
    if (await onUpdate(body)) setEditing(false)
  }

  function cancel() {
    setBody(note.body)
    setEditing(false)
  }

  const Root = compact ? 'div' : 'article'
  return (
    <Root className={compact ? 'hover-note' : cn('note', isFresh(note.created_at) && slideUpIn)} data-note-id={note.id}>
      {/* Provenance is never subtle: every note shows a badge, and AI text gets its own background. */}
      <Card
        size="sm"
        className={cn(
          'bg-glass-strong ring-glass-border',
          note.provenance !== 'human' && 'bg-provenance-llm-surface',
          active && 'ring-2 ring-primary',
          className,
        )}
      >
        <CardHeader className="flex items-center justify-between">
          <ProvenanceBadge provenance={note.provenance} />
          {!compact && anchor && (
            <Button variant="link" size="xs" onClick={onSelect}>
              p. {anchor.page}
            </Button>
          )}
        </CardHeader>

        <CardContent className="flex flex-col gap-2">
          {!compact && anchor && (
            // Two lines are enough to recognise the passage; the rest is in the title and on the highlight itself.
            <blockquote
              className="line-clamp-2 cursor-pointer border-l-2 pl-2 text-muted-foreground"
              title={anchor.quoted_text}
              onClick={onSelect}
            >
              {anchor.quoted_text}
            </blockquote>
          )}
          {editing ? (
            <Textarea
              autoFocus
              aria-label="Edit note"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              onKeyDown={(e) => e.key === 'Escape' && cancel()}
            />
          ) : note.body ? (
            <p className={cn('whitespace-pre-wrap', compact && 'line-clamp-6')}>{note.body}</p>
          ) : (
            compact &&
            anchor && (
              <p className="line-clamp-2 text-muted-foreground" title={anchor.quoted_text}>
                {anchor.quoted_text}
              </p>
            )
          )}
          {!compact && <NoteCharts note={note} />}
          <HighlightColorPicker value={note.color} onChange={(hex) => void onColorChange(hex)} />
        </CardContent>

        <CardFooter className="justify-end gap-2">
          <span className="sr-only" role="status">
            {copied ? 'Quote copied.' : ''}
          </span>
          {copyError && (
            <p role="alert" className="mr-auto text-xs text-destructive">
              {copyError}
            </p>
          )}
          {editing ? (
            <>
              <Button variant="ghost" size="sm" onClick={cancel}>
                Cancel
              </Button>
              <Button size="sm" onClick={() => void save()}>
                Save
              </Button>
            </>
          ) : (
            <>
              {anchor?.quoted_text && (
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Copy quote"
                  onClick={() => void copyQuote(anchor.quoted_text)}
                >
                  {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
                </Button>
              )}
              {!compact && (
                <Button variant="ghost" size="sm" onClick={() => setAttachingChart(true)}>
                  <ChartColumn aria-hidden />
                  Attach chart
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
                Edit
              </Button>
              <Button variant="ghost" size="sm" className="text-destructive" onClick={() => void onDelete()}>
                Delete
              </Button>
            </>
          )}
        </CardFooter>
      </Card>
      {!compact && <AttachChartDialog note={note} open={attachingChart} onOpenChange={setAttachingChart} />}
    </Root>
  )
}
