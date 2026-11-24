import type { ChartSpec, ChatScope, ChatSource, NoteSource, ChatAnswer as SavedAnswer } from '@/entities'
import { ChatAnswer } from './ChatAnswer'
import { ChatChart } from './ChatChart'
import { chartTitle } from './chartTitle'
import { splitCitations } from '@/components/citations'
import type { threadOrder } from './threads'

/** Labels whose chunk or note still exists; markers for any other label render as plain text. */
const knownLabels = (answer: SavedAnswer) =>
  new Set([...answer.sources, ...answer.notes].flatMap((source) => (source ? [source.label] : [])))

/** One saved answer in the thread, with its follow-up, chart and footer. */
export function ThreadAnswer({
  answer,
  reply,
  scope,
  closed,
  paperLabel,
  onCite,
  onFollowUp,
}: {
  answer: SavedAnswer
  reply: ReturnType<typeof threadOrder>['placed'][number]['reply']
  scope: ChatScope
  closed: boolean
  paperLabel?: (paperId: string) => string
  onCite: (source: ChatSource | NoteSource) => void
  onFollowUp: (answerId: string) => void
}) {
  return (
    <ChatAnswer
      outputId={answer.id}
      checkable={scope.kind !== 'hit' && !answer.chart_spec}
      hasCheck={answer.has_check}
      parentId={answer.parent_id}
      reply={reply}
      question={answer.question}
      readings={answer.readings}
      wholePaper={answer.whole_paper}
      sources={answer.sources}
      notes={answer.notes}
      notesUsed={answer.notes_used}
      notesTotal={answer.notes_total}
      segments={splitCitations(answer.content, knownLabels(answer))}
      footer={{
        model: answer.model,
        connectionName: answer.connection_name,
        promptVersion: answer.prompt_version,
        skillLabel: answer.skill_label,
        lens: answer.lens,
      }}
      paperLabel={paperLabel}
      onCite={onCite}
      followUp={scope.kind !== 'workspace' ? { onClick: () => onFollowUp(answer.id), disabled: closed } : undefined}
      suggestions={{ scope, saved: answer.saved_notes }}
    >
      {answer.chart_spec && <ChatChart spec={answer.chart_spec as ChartSpec} title={chartTitle(answer.content)} />}
    </ChatAnswer>
  )
}
