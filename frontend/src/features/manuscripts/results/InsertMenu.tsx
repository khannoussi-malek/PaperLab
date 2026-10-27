import { ChevronDown } from 'lucide-react'
import { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { TableDialog } from './TableDialog'
import type { InsertResult } from './useInsertBlock'

/** The editor toolbar's Insert button: a table (chart comes with its own item). */
export function InsertMenu({ manuscriptId, labelTexts, onInsert }: {
  manuscriptId: string
  labelTexts: () => string[]
  onInsert: (code: string, packages: string[]) => Promise<InsertResult>
}) {
  const [dialog, setDialog] = useState<'table' | null>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  // An insert leaves you typing in the editor; cancelling or Esc goes back to the Insert button.
  const closed = (inserted: boolean) => {
    const editor = inserted ? trigger.current?.closest('section')?.querySelector<HTMLElement>('.cm-content') : null
    ;(editor ?? trigger.current)?.focus()
  }
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button ref={trigger} size="sm" variant="outline">Insert<ChevronDown aria-hidden /></Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => setDialog('table')}>Table…</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {dialog === 'table' && <TableDialog open onOpenChange={(o) => !o && setDialog(null)} manuscriptId={manuscriptId} labelTexts={labelTexts} onInsert={onInsert} onClosed={closed} />}
    </>
  )
}
