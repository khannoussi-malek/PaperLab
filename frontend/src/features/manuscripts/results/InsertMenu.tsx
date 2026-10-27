import { ChevronDown } from 'lucide-react'
import { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { ChartDialog } from './ChartDialog'
import { TableDialog } from './TableDialog'
import type { InsertResult } from './useInsertBlock'

/** The editor toolbar's Insert button: a table or a chart. */
export function InsertMenu({ manuscriptId, labelTexts, filePaths, onInsert }: {
  manuscriptId: string
  labelTexts: () => string[]
  filePaths: () => string[]
  onInsert: (code: string, packages: string[]) => Promise<InsertResult>
}) {
  const [dialog, setDialog] = useState<'table' | 'chart' | null>(null)
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
          <DropdownMenuItem onSelect={() => setDialog('chart')}>Chart…</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {dialog === 'table' && <TableDialog open onOpenChange={(o) => !o && setDialog(null)} manuscriptId={manuscriptId} labelTexts={labelTexts} onInsert={onInsert} onClosed={closed} />}
      {dialog === 'chart' && <ChartDialog open onOpenChange={(o) => !o && setDialog(null)} manuscriptId={manuscriptId} labelTexts={labelTexts} filePaths={filePaths} onInsert={onInsert} onClosed={closed} />}
    </>
  )
}
