import type { ChatScope, ChatSource, NoteSource } from '@/entities'
import { ChatAnswer } from './ChatAnswer'
import { ProblemAlert } from './ProblemAlert'
import type { threadOrder } from './threads'
import type { useChatStream } from './useChatStream'

/** The answer being asked now: at the end of the thread it follows up, or last, until its saved copy is listed. */
export function LiveAnswer({
  scope,
  stream,
  liveReply,
  busy,
  retry,
  paperLabel,
  onCite,
}: {
  scope: ChatScope
  stream: ReturnType<typeof useChatStream>['stream']
  liveReply: ReturnType<typeof threadOrder>['liveReply']
  busy: boolean
  retry: ReturnType<typeof useChatStream>['retry']
  paperLabel?: (paperId: string) => string
  onCite: (source: ChatSource | NoteSource) => void
}) {
  return (
    <ChatAnswer
      question={stream.question}
      readings={stream.readings}
      readingsTotal={stream.readings[0]?.total}
      readingsLive={stream.status === 'sources'}
      parentId={stream.parentId}
      reply={liveReply}
      wholePaper={stream.wholePaper}
      sources={stream.sources}
      notes={stream.notes}
      notesUsed={stream.notesUsed}
      notesTotal={stream.notesTotal}
      segments={stream.segments}
      footer={
        // A spoken answer's saved id arrives before its model; the footer waits for the saved copy.
        stream.done?.model
          ? {
              model: stream.done.model,
              connectionName: stream.done.connection_name,
              promptVersion: stream.done.prompt_version,
              skillLabel: stream.done.skill_label,
              lens: stream.done.lens,
            }
          : null
      }
      pending={busy}
      animate
      paperLabel={paperLabel}
      onCite={onCite}
    >
      {stream.problem && <ProblemAlert scope={scope} problem={stream.problem} onRetry={retry} />}
    </ChatAnswer>
  )
}
