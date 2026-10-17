import { useRef, useState, type ReactNode } from 'react'
import { Info } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { GLOSSARY, type GlossaryKey } from './glossary'

/** A jargon word with its plain-language explanation. Opens on keyboard focus and on tap (click toggles), and a
 * tap never reaches a clickable parent row. Never nest it inside a button, link or tab trigger. */
export function Term({ term, children }: { term: GlossaryKey; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  // A real tap focuses (which opens) before it clicks; remember the state from before the press so the click
  // doesn't immediately close what the press just opened.
  const openBeforePress = useRef<boolean | null>(null)
  return (
    <TooltipProvider>
      <Tooltip open={open} onOpenChange={setOpen}>
        <TooltipTrigger asChild>
          <button
            type="button"
            className="inline-flex items-center gap-1 underline decoration-dotted underline-offset-4 cursor-help"
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
