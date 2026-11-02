import { useEffect } from 'react'
import { ListChecks } from 'lucide-react'
import type { ChatSource, Note } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { ProblemAlert } from '@/features/chat/ProblemAlert'
import { RemoteConfirmDialog } from '@/features/manuscripts/review/RemoteConfirm'
import { CheckResult } from './CheckResult'
import { isExitTest } from '@/features/notes/noteKinds'
import { exitTestLabel } from './exitTest'
import { usePaperChecks } from './queries'
import { useCheckStream } from './useCheckStream'

const NOT_YOURS = 'Only text you wrote can be checked. This note came from AI.'
const BUSY = new Set(['sources', 'streaming'])

type Props = { note: Note; paperId: string; onCite: (source: ChatSource) => void }

/** A note card's check (§3.8): the button, the check being read, and the latest saved check. Only exit-test kinds. */
export function NoteCheck({ note, paperId, onCite }: Props) {
  const kind = isExitTest(note.kind) ? note.kind : null
  const { stream, run, cancelConfirm } = useCheckStream(note.id, paperId, kind ?? 'summary')
  const check = usePaperChecks(paperId).data?.find((c) => c.note_id === note.id)
  const settled = stream.status === 'done' || stream.status === 'error'
  // A finished or refused stream describes the text as it was; once the note changes, the saved check (now out of
  // date) takes over and a refusal clears.
  useEffect(() => {
    if (settled) cancelConfirm()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only a changed body should reset it
  }, [note.body])
  if (!kind) return null

  const label = exitTestLabel(kind)
  const busy = BUSY.has(stream.status)
  const live = busy || stream.status === 'error'
  const saved = check && !busy && (stream.status === 'idle' || stream.status === 'error' || !check.stale) ? check : undefined
  const streamed = (live || (stream.status === 'done' && !saved)) && stream.lines.length > 0
  const again = () => void run()

  const button = (
    <Button variant="secondary" size="sm" disabled={note.provenance !== 'human'} onClick={again}>
      <ListChecks aria-hidden />
      Check against the paper
    </Button>
  )
  return (
    <div className="flex flex-col gap-2 px-4 pb-3">
      {!check && !busy && !stream.problem?.retryable && stream.status !== 'done' && (
        note.provenance === 'human' ? (
          button
        ) : (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                {/* A disabled button gets no focus events, so the tooltip hangs on a focusable wrapper. */}
                <span tabIndex={0} className="inline-block self-start rounded-md">
                  {button}
                </span>
              </TooltipTrigger>
              <TooltipContent>{NOT_YOURS}</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )
      )}
      {busy && (
        <p role="status" className="text-sm text-muted-foreground">
          {stream.status === 'sources' ? 'Reading the paper…' : `Checking your ${label}…`}
        </p>
      )}
      {saved && (
        <CheckResult
          label={label}
          lines={saved.lines}
          dropped={saved.dropped}
          sources={saved.sources}
          tooltip={`AI · ${saved.model} · check prompt v${saved.prompt_version} · ${saved.whole_paper ? 'whole lens' : `${saved.sources.filter(Boolean).length} passages`}`}
          stale={saved.stale}
          busy={busy}
          onCheckAgain={again}
          onCite={onCite}
        />
      )}
      {streamed && (
        <CheckResult
          label={label}
          lines={stream.lines}
          dropped={0}
          sources={stream.sources ?? []}
          tooltip="AI check, in progress"
          stale={false}
          busy={busy}
          onCheckAgain={again}
          onCite={onCite}
        />
      )}
      {stream.problem && (
        // one way to check again: a result on screen has Check again, so the alert doesn't add Retry beside it
        <ProblemAlert scope={{ kind: 'paper', id: paperId }} problem={saved || streamed ? { ...stream.problem, retryable: false } : stream.problem} onRetry={again} />
      )}
      <RemoteConfirmDialog what="note" host={stream.status === 'confirm' ? stream.host : null} onSend={() => void run(true)} onCancel={cancelConfirm} />
    </div>
  )
}
