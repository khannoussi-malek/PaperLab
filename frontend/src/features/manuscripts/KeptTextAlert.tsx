import type { ReactNode } from 'react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import type { KeptText } from './keptTexts'

type Props = { path: string; kept: KeptText; action: ReactNode; onDiscard: () => void }

/** Text a closed (or interrupted) save left behind: reopen it with `action`, or let it go. */
export function KeptTextAlert({ path, kept, action, onDiscard }: Props) {
  return (
    <Alert variant="destructive" className="mb-2 w-auto">
      <AlertDescription className="flex flex-wrap items-center gap-3">
        <span>
          Your changes to {path} were not saved{kept.reason === 'conflict' ? ': the file changed somewhere else' : ''}. They are
          kept here until you use them or discard them.
        </span>
        {action}
        <Button size="sm" variant="ghost" onClick={onDiscard}>Discard</Button>
      </AlertDescription>
    </Alert>
  )
}
