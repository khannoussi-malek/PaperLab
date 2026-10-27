import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
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
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button size="sm" variant="outline">Insert<ChevronDown aria-hidden /></Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => setDialog('table')}>Table…</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {dialog === 'table' && <TableDialog open onOpenChange={(o) => !o && setDialog(null)} manuscriptId={manuscriptId} labelTexts={labelTexts} onInsert={onInsert} />}
    </>
  )
}
