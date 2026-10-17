import type { ReactNode } from 'react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

/** A tooltip on a control: opens on focus and on hover, and the control itself is the trigger (aria-describedby). */
export function Hint({ hint, children }: { hint?: string; children: ReactNode }) {
  if (!hint) return <>{children}</>
  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>{children}</TooltipTrigger>
        <TooltipContent>{hint}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
