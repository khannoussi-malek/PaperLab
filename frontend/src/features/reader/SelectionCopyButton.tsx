import { Check, Copy } from 'lucide-react'
import { type CSSProperties, useEffect, useState } from 'react'
import { popIn } from '@/components/motion'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type Props = {
  /** Placed by the caller, under the last line of the selection. */
  style: CSSProperties
  /** Resolves false when the browser refused; the reader shows the reason in its own alert. */
  onCopy: () => Promise<boolean>
}

/** The one visible way to copy a passage without saving it: floats under a fresh selection until it is used or lost. */
export function SelectionCopyButton({ style, onCopy }: Props) {
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) return
    const timer = setTimeout(() => setCopied(false), 1500)
    return () => clearTimeout(timer)
  }, [copied])

  return (
    // preventDefault on mousedown keeps the selection alive while the button is pressed.
    <Button
      size="icon-sm"
      aria-label="Copy text"
      // The page overlay is click-through so highlights never swallow a selection; this button has to opt back in.
      className={cn('selection-copy pointer-events-auto absolute z-20 shadow-lg', popIn)}
      style={style}
      onMouseDown={(event) => event.preventDefault()}
      onClick={() => void onCopy().then(setCopied)}
    >
      {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
    </Button>
  )
}
