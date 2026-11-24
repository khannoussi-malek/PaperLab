import { MessageSquareText } from 'lucide-react'
import type { ChatScope } from '@/entities'
import { Button } from '@/components/ui/button'
import { pressable } from '@/components/motion'
import { cn } from '@/lib/utils'

// What an empty chat offers, by scope: a workspace's starter questions look across its papers.
const EMPTY_CHAT = {
  paper: {
    heading: 'Ask this paper',
    help: 'Answers cite the passages they use. Click a citation to see it in the paper.',
    starters: ['Summarize the main contribution', 'What method do they use?', 'What are the limitations?'],
  },
  workspace: {
    heading: 'Ask this workspace',
    help: 'Answers cite passages from its papers and your notes. Click a citation to open it in the paper.',
    starters: ['Compare their main contributions', 'How do their methods differ?', 'What do my notes say about them?'],
  },
  hit: {
    heading: 'Ask about this paper',
    help: 'Answers use its abstract, or the full text once the paper has a file.',
    starters: ['Summarize the main contribution', 'What method do they use?', 'Is this relevant to my question?'],
  },
}

type EmptyChatProps = { kind: ChatScope['kind']; disabled: boolean; onAsk: (question: string) => void }

export function EmptyChat({ kind, disabled, onAsk }: EmptyChatProps) {
  const { heading, help, starters } = EMPTY_CHAT[kind]
  return (
    <div className="m-auto flex w-full max-w-xs flex-col items-center gap-3 py-6 text-center">
      <span className="flex size-10 items-center justify-center rounded-full bg-provenance-llm-surface text-provenance-llm">
        <MessageSquareText aria-hidden className="size-5" />
      </span>
      <h2 className="font-heading text-xl font-semibold">{heading}</h2>
      <p className="text-sm text-muted-foreground">{help}</p>
      <ul aria-label="Suggested questions" className="mt-1 flex w-full flex-col gap-2">
        {starters.map((starter) => (
          <li key={starter}>
            <Button
              variant="outline"
              size="sm"
              className={cn('h-auto w-full justify-start bg-glass-strong py-1.5 text-left whitespace-normal', pressable)}
              disabled={disabled}
              onClick={() => onAsk(starter)}
            >
              {starter}
            </Button>
          </li>
        ))}
      </ul>
    </div>
  )
}
