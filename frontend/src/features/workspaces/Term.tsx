import { useRef, useState, type ReactNode } from 'react'
import { Info } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { GLOSSARY, type GlossaryKey } from './glossary'

/** A jargon word with its plain-language explanation. Opens on keyboard focus, after a short hover delay, and on
 * tap (click toggles); a tap never reaches a clickable parent row. Never nest it inside a button, link or tab trigger. */
export function Term({ term, children }: { term: GlossaryKey; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  // A touch tap can open the tooltip on press (Radix ignores focus that follows a pointer press, but not touch
  // hover); remember the state from before the press so the click doesn't immediately close what it just opened.
  const openBeforePress = useRef<boolean | null>(null)
  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip open={open} onOpenChange={setOpen}>
        <TooltipTrigger asChild>
          <button
            type="button"
            className="inline-flex items-center gap-1 underline decoration-dotted underline-offset-4 cursor-help rounded-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            onPointerDown={() => { openBeforePress.current = open }}
            onClick={(event) => {
              event.stopPropagation()
              event.preventDefault()
              setOpen(!(openBeforePress.current ?? open))
              openBeforePress.current = null
            }}
          >
            {children}
            <Info className="size-3" aria-hidden />
          </button>
        </TooltipTrigger>
        <TooltipContent>{GLOSSARY[term]}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
