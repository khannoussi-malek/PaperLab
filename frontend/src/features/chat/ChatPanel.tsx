import { useEffect, useRef, useState } from 'react'
import type { ChatSource, ChatAnswer as SavedAnswer } from '@/api/client'
import { useChatHistory, useReindexPaper } from '@/api/queries'
import { Alert, AlertAction, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { ChatAnswer } from './ChatAnswer'
import { splitCitations } from './citations'
import { useChatStream, type ChatProblem } from './useChatStream'

const MAX_QUESTION = 2000 // the API's limit (spec §3.10)

/** Labels whose chunk still exists; markers for any other label render as plain text. */
const knownLabels = (answer: SavedAnswer) => new Set(answer.sources.flatMap((source) => (source ? [source.label] : [])))

type Props = {
  paperId: string
  onCite: (source: ChatSource) => void
}

export function ChatPanel({ paperId, onCite }: Props) {
  const history = useChatHistory(paperId)
  const { stream, ask, retry } = useChatStream(paperId)
  const [question, setQuestion] = useState('')
  const listRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const wasBusy = useRef(false)
  const answers = history.data ?? []
  const busy = stream.status === 'sources' || stream.status === 'streaming'
  // A saved answer comes back in the history, so the live copy hides instead of showing twice.
  const showLive = stream.status !== 'idle' && !answers.some((answer) => answer.id === stream.done?.output_id)

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [answers.length, stream.status])

  // Enter disables the Textarea while busy, so the browser blurs it to <body>; bring focus back once it clears.
  useEffect(() => {
    if (wasBusy.current && !busy) textareaRef.current?.focus()
    wasBusy.current = busy
  }, [busy])

  function submit() {
    const text = question.trim()
    if (!text || busy) return
    setQuestion('')
    void ask(text)
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div ref={listRef} className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4">
        {history.error && (
          <Alert variant="destructive" className={cn('border-glass-border')}>
            <AlertDescription>{history.error.message}</AlertDescription>
          </Alert>
        )}
        {answers.length === 0 && !showLive && (
          <p className="text-sm text-muted-foreground">Ask a question about this paper. Answers cite the passages they use.</p>
        )}
        {answers.map((answer) => (
          <ChatAnswer
            key={answer.id}
            outputId={answer.id}
            question={answer.question}
            wholePaper={answer.whole_paper}
            sources={answer.sources}
            segments={splitCitations(answer.content, knownLabels(answer))}
            footer={{ model: answer.model, promptVersion: answer.prompt_version }}
            onCite={onCite}
          />
        ))}
        {showLive && (
          <ChatAnswer
            question={stream.question}
            wholePaper={stream.wholePaper}
            sources={stream.sources}
            segments={stream.segments}
            footer={stream.done && { model: stream.done.model, promptVersion: stream.done.prompt_version }}
            pending={busy}
            onCite={onCite}
          >
            {stream.problem && <ProblemAlert paperId={paperId} problem={stream.problem} onRetry={retry} />}
          </ChatAnswer>
        )}
      </div>

      <form
        className="flex flex-col gap-2 border-t border-glass-border p-3"
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <Textarea
          ref={textareaRef}
          aria-label="Question"
          placeholder="Ask about this paper. Enter sends, Shift+Enter adds a line."
          rows={2}
          maxLength={MAX_QUESTION}
          value={question}
          disabled={busy}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault()
              submit()
            }
          }}
        />
        <Button type="submit" size="sm" className="self-end" disabled={busy || !question.trim()}>
          Ask
        </Button>
      </form>
    </div>
  )
}

function ProblemAlert({ paperId, problem, onRetry }: { paperId: string; problem: ChatProblem; onRetry: () => void }) {
  const reindex = useReindexPaper(paperId)
  const message = reindex.isSuccess
    ? 'Re-indexing started. Ask again once the paper is ready.'
    : (reindex.error?.message ?? problem.message)
  return (
    <Alert variant="destructive" className={cn('chat-error border-glass-border')}>
      <AlertDescription>{message}</AlertDescription>
      <AlertAction>
        {problem.retryable && (
          <Button variant="outline" size="xs" onClick={onRetry}>
            Retry
          </Button>
        )}
        {problem.reindex && !reindex.isSuccess && (
          <Button variant="outline" size="xs" disabled={reindex.isPending} onClick={() => reindex.mutate()}>
            Re-index
          </Button>
        )}
      </AlertAction>
    </Alert>
  )
}
