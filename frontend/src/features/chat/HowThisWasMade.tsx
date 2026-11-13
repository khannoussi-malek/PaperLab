import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { Collapsible } from 'radix-ui'
import type { AnswerPassage, AnswerProvenance, McpNoteProvenance } from '@/api/client'
import { useAnswerProvenance, useNoteProvenance } from '@/api/queries'
import { LENS_LABELS } from '@/features/lenses/lenses'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const STATE_TEXT: Record<AnswerPassage['state'], string> = {
  current: 'Still in the paper',
  changed: 'No longer matches the paper',
  not_recorded: 'Not recorded for answers saved before this was added.',
  not_kept: "PaperLab didn't keep a copy of this passage.",
  paper_removed: 'The paper was removed from your library.',
}
const OUT_OF_DATE = 'Some passages this answer cited have changed since. Ask again for a current answer.'
const MCP_NOTE = 'Added from Claude Desktop.'
const LOAD_FAILED = 'Could not load how this was made.'

type Props = { outputId: string } | { noteId: string }

/** The disclosure under a saved AI answer or AI note. Closed by default; its record is read only once it opens. */
export function HowThisWasMade(props: Props) {
  const [open, setOpen] = useState(false)
  return (
    <Collapsible.Root open={open} onOpenChange={setOpen} className="flex flex-col gap-1 text-xs">
      <Collapsible.Trigger asChild>
        <Button variant="ghost" size="xs" className="self-start text-muted-foreground">
          How this was made
          <ChevronDown aria-hidden className={cn('transition-transform', open && 'rotate-180')} />
        </Button>
      </Collapsible.Trigger>
      <Collapsible.Content className="flex flex-col gap-2 rounded-lg bg-background/60 p-3">
        {'outputId' in props ? <AnswerDetails outputId={props.outputId} /> : <NoteDetails noteId={props.noteId} />}
      </Collapsible.Content>
    </Collapsible.Root>
  )
}

// Mounted only while the disclosure is open, so the query starts with it and not before.
function AnswerDetails({ outputId }: { outputId: string }) {
  const query = useAnswerProvenance(outputId, true)
  if (query.error) return <p role="alert">{LOAD_FAILED}</p>
  return query.data ? <Provenance view={query.data} /> : <p className="text-muted-foreground">Loading…</p>
}

function NoteDetails({ noteId }: { noteId: string }) {
  const query = useNoteProvenance(noteId, true)
  if (query.error) return <p role="alert">{LOAD_FAILED}</p>
  if (!query.data) return <p className="text-muted-foreground">Loading…</p>
  return isMcp(query.data) ? <p>{MCP_NOTE}</p> : <Provenance view={query.data} />
}

const isMcp = (view: AnswerProvenance | McpNoteProvenance): view is McpNoteProvenance => 'source' in view

function Provenance({ view }: { view: AnswerProvenance }) {
  return (
    <>
      {view.out_of_date && <p className="rounded-md bg-amber-100 p-2 text-amber-950 dark:bg-amber-950/60 dark:text-amber-100">{OUT_OF_DATE}</p>}
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        <dt className="text-muted-foreground">Model</dt>
        <dd>{view.model}</dd>
        <dt className="text-muted-foreground">Connection</dt>
        <dd>{view.connection_name ?? '—'}</dd>
        <dt className="text-muted-foreground">Prompt version</dt>
        <dd>{view.prompt_version}</dd>
        {view.skill_label && (
          <>
            <dt className="text-muted-foreground">Skill</dt>
            <dd>{view.skill_label}</dd>
          </>
        )}
        {view.lens !== 'full' && (
          <>
            <dt className="text-muted-foreground">Lens</dt>
            <dd>{LENS_LABELS[view.lens]}</dd>
          </>
        )}
        <dt className="text-muted-foreground">Made</dt>
        <dd>{new Date(view.created_at).toLocaleString()}</dd>
      </dl>
      {view.passages.length > 0 && (
        <ul className="flex flex-col gap-1.5">
          {view.passages.map((passage) => (
            <li key={passage.label} className="flex flex-col">
              <span>
                <span className="font-medium">{passage.label}</span>
                {passageWhere(passage) && <span className="text-muted-foreground"> · {passageWhere(passage)}</span>}
              </span>
              <span className={cn(passage.state === 'changed' && 'text-amber-800 dark:text-amber-300')}>{STATE_TEXT[passage.state]}</span>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

/** "Paper A, p. 4", with whichever parts the record kept. */
const passageWhere = (passage: AnswerPassage) =>
  [passage.paper_title, passage.page === null ? null : `p. ${passage.page}`].filter(Boolean).join(', ')
