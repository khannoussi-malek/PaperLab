import { useState } from 'react'
import type { AnswerCheck as Check, AnswerCheckSentence } from '@/entities'
import { ApiError, isConflict } from '@/services/api'
import { useAnswerCheck, useStartAnswerCheck } from '@/services/queries'
import { Button } from '@/components/ui/button'
import { RemoteConfirmDialog } from '@/components/RemoteConfirm'
import { cn } from '@/lib/utils'
import { chip, type Tone } from './answerCheckMarks'

const NOT_CHECKABLE = "This answer was saved before PaperLab kept copies of its passages, so it can't be checked."
const FAILED = 'The check stopped before it finished. Check again.'
const START_FAILED = "Couldn't start the check."
// The held-out gate's two misses (PR #224): say them where the verdicts are read.
const CAVEAT =
  'A first read, not proof: it can miss a figure moved to the wrong group or a claim stated more strongly than its ' +
  'passage. Read the quotes.'
const TONES: Record<Tone, string> = {
  quiet: 'text-muted-foreground',
  warn: 'text-amber-700 dark:text-amber-300',
  bad: 'text-destructive font-medium',
  muted: 'text-muted-foreground',
}

const startError = (e: unknown) =>
  isConflict(e, 'answer_not_checkable') ? NOT_CHECKABLE : e instanceof ApiError ? e.message : START_FAILED

/** "Check this answer" under a saved chat answer (M34): each cited sentence judged against its own passages. */
export function AnswerCheck({ outputId, known = false }: { outputId: string; known?: boolean }) {
  const [started, setStarted] = useState(false)
  const query = useAnswerCheck(outputId, known || started)
  const start = useStartAnswerCheck(outputId)
  const [host, setHost] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const run = async (confirmRemote: boolean) => {
    setHost(null)
    setError(null)
    try {
      await start.mutateAsync(confirmRemote)
      setStarted(true)
    } catch (e) {
      if (isConflict(e, 'remote_model_needs_confirm')) setHost(String((e as ApiError).body.host ?? 'a remote model'))
      else setError(startError(e))
    }
  }
  const check = query.data
  const running = check?.state === 'running'
  return (
    <section aria-label="Answer check" className="flex flex-col gap-2 text-xs">
      {check ? <Summary check={check} /> : null}
      <div className="flex items-center gap-2">
        {!running && !query.isLoading && (
          <Button type="button" variant="ghost" size="xs" className="self-start text-muted-foreground"
            disabled={start.isPending} onClick={() => run(false)}>
            {check ? 'Check again' : 'Check this answer'}
          </Button>
        )}
        {error && <span role="alert" className="text-destructive">{error}</span>}
      </div>
      {check && <Rows sentences={check.sentences} />}
      <RemoteConfirmDialog what="answer" host={host} onSend={() => run(true)} onCancel={() => setHost(null)} />
    </section>
  )
}

function Summary({ check }: { check: Check }) {
  if (check.state === 'running') {
    const toCheck = check.sentences.filter((s) => s.state === 'pending' || s.state === 'done')
    const done = toCheck.filter((s) => s.state === 'done').length
    return <p aria-live="polite" className="text-muted-foreground">{`Checking ${done} of ${toCheck.length} sentences…`}</p>
  }
  if (check.state === 'failed') return <p role="alert" className="text-destructive">{FAILED}</p>
  const when = new Date(check.created_at).toLocaleString()
  const by = check.connection_name ? `${check.model} (${check.connection_name})` : check.model
  return (
    <>
      <p className="text-muted-foreground">
        {`Checked by ${by} · ${when} · ${check.summary}`}
        {check.limit_hit && ' · only the first 20 cited sentences were checked'}
      </p>
      <p className="text-muted-foreground italic">{CAVEAT}</p>
    </>
  )
}

function Rows({ sentences }: { sentences: AnswerCheckSentence[] }) {
  return (
    <ol className="flex flex-col gap-1.5 rounded-lg bg-background/60 p-3">
      {sentences.map((sentence) => <Row key={sentence.index} sentence={sentence} />)}
    </ol>
  )
}

function Row({ sentence }: { sentence: AnswerCheckSentence }) {
  const mark = chip(sentence)
  const notes = [
    sentence.confidence === 'low' ? 'low confidence: no quote from the passage backs it' : null,
    sentence.shortened ? 'judged on a shortened passage' : null,
  ].filter(Boolean)
  return (
    <li className="flex flex-col gap-0.5" data-verdict={sentence.verdict ?? sentence.state}>
      <span>
        <span className="text-foreground">{sentence.text}</span>{' '}
        <span className={cn('whitespace-nowrap', TONES[mark.tone])}>
          <span aria-hidden>{mark.symbol}</span> {mark.word}
        </span>{' '}
        {sentence.state === 'done' && <span className="text-provenance-llm">AI check</span>}
      </span>
      {sentence.state === 'done' && sentence.reason && <span className="text-muted-foreground">{sentence.reason}</span>}
      {sentence.quote && (
        <span className="text-muted-foreground">
          {`"${sentence.quote}"`}{sentence.quote_label && ` [${sentence.quote_label}]`}
        </span>
      )}
      {notes.length > 0 && <span className="text-muted-foreground italic">{notes.join(' · ')}</span>}
    </li>
  )
}
