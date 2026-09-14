import { Sparkles } from 'lucide-react'
import type { CSSProperties } from 'react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

type Props = {
  canSave: boolean
  saving: boolean
  /** A failed save's readable reason. Shown right under the button, where the user is already looking. */
  error: string | null
  style: CSSProperties
  onSave: () => void
}

export function SaveAsNoteButton({ canSave, saving, error, style, onSave }: Props) {
  const button = (
    <Button size="sm" className="shadow-lg" disabled={!canSave || saving} onClick={onSave}>
      <Sparkles aria-hidden />
      Save as note
    </Button>
  )
  return (
    // preventDefault on mousedown keeps the selection alive while the button is pressed.
    <div
      className="save-as-note absolute z-20 flex flex-col items-start gap-1"
      style={style}
      onMouseDown={(e) => e.preventDefault()}
    >
      {canSave ? (
        button
      ) : (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              {/* A disabled button gets no pointer or focus events, so the tooltip hangs on a focusable wrapper. */}
              <span tabIndex={0} className="inline-block rounded-md">
                {button}
              </span>
            </TooltipTrigger>
            <TooltipContent>Include a cited passage [C…] to anchor this note</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )}
      {error && (
        <Alert variant="destructive" className={cn('w-max max-w-64 border-glass-border shadow-lg')}>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}
