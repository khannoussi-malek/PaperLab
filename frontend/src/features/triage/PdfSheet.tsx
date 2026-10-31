import { FileText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { TriagePdf } from './TriagePdf'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  paperId: string
  target: { page: number; n: number } | null
  onInteract: () => void
  initialPage?: number
  onPage?: (page: number) => void
  /** `P` opens the sheet with no trigger to return to: focus goes back to the desk. */
  returnFocus?: () => void
}

/** The narrow desk's PDF: a button under the card and a full-screen sheet. Esc closes the sheet, not the desk. */
export function PdfSheet({ open, onOpenChange, paperId, target, onInteract, initialPage, onPage, returnFocus }: Props) {
  return (
    <>
      <Button type="button" variant="outline" className="min-h-11 self-start" onClick={() => onOpenChange(true)}>
        <FileText aria-hidden />
        Open PDF
      </Button>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="top-0 left-0 h-dvh max-h-none w-screen max-w-none translate-x-0 translate-y-0 gap-2 rounded-none p-2 sm:max-w-none"
          onCloseAutoFocus={(e) => { e.preventDefault(); returnFocus?.() }}
          onKeyDown={(e) => { // P closes the sheet it opened; the portal sits outside the desk's own key listener
            if (e.key.toLowerCase() === 'p' && !e.ctrlKey && !e.metaKey && !e.altKey && !(e.target as Element).closest('input,textarea,select,[contenteditable]')) { e.preventDefault(); onOpenChange(false) }
          }}
        >
          <DialogTitle className="sr-only">PDF</DialogTitle>
          <DialogDescription className="sr-only">The paper's PDF. Close it to go back to the card.</DialogDescription>
          <TriagePdf key={paperId} paperId={paperId} active target={target} initialPage={initialPage} onPage={(p) => onPage?.(p)} onInteract={onInteract} />
        </DialogContent>
      </Dialog>
    </>
  )
}
