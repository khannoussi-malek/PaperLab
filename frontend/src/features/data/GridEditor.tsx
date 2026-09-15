import {
  ArrowDownToLine,
  ArrowLeftToLine,
  ArrowRightToLine,
  ArrowUpToLine,
  EllipsisVertical,
  Merge,
  Plus,
  Rows3,
  Ruler,
  SplitSquareHorizontal,
  Trash2,
} from 'lucide-react'
import { useEffect, useRef } from 'react'
import type { CellFocus } from '@/lib/route'
import { glass } from '@/components/glass'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import {
  deleteColumn,
  deleteRow,
  editCell,
  fillDown,
  type Grid,
  type GridColumn,
  insertColumn,
  insertRow,
  isEdited,
  mergeColumns,
  renameColumn,
  setUnit,
  splitColumn,
  useRowAsHeader,
} from './gridModel'

type Props = {
  grid: Grid
  onChange: (next: Grid) => void
  /** A cell to scroll to and focus once, when the page opens from a chart point. */
  focus?: CellFocus | null
}

const inputClass = 'h-8 min-w-24 border-0 bg-transparent shadow-none tabular-nums focus-visible:ring-2'
const menuSurface = cn(glass, 'bg-glass-strong ring-glass-border')

function ColumnMenu({ grid, column, onChange }: { grid: Grid; column: number; onChange: (next: Grid) => void }) {
  const current = grid.columns[column]
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={`Column ${column + 1} actions`} title={`Column ${column + 1} actions`}>
          <EllipsisVertical aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className={menuSurface}>
        <DropdownMenuItem disabled={column >= grid.columns.length - 1} onSelect={() => onChange(mergeColumns(grid, column))}>
          <Merge aria-hidden />
          Merge with next column
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => onChange(splitColumn(grid, column, 1))}>
          <SplitSquareHorizontal aria-hidden />
          Split after first word
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => onChange(fillDown(grid, column))}>
          <ArrowDownToLine aria-hidden />
          Fill down
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={() => {
            const next = window.prompt(`Unit for ${current.name}`, current.unit ?? '')
            if (next === null) return
            onChange(setUnit(grid, column, next.trim() === '' ? null : next.trim()))
          }}
        >
          <Ruler aria-hidden />
          Set unit…
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => onChange(insertColumn(grid, column))}>
          <ArrowLeftToLine aria-hidden />
          Insert column left
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => onChange(insertColumn(grid, column + 1))}>
          <ArrowRightToLine aria-hidden />
          Insert column right
        </DropdownMenuItem>
        <DropdownMenuItem variant="destructive" onSelect={() => onChange(deleteColumn(grid, column))}>
          <Trash2 aria-hidden />
          Delete column
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function RowMenu({ grid, row, onChange }: { grid: Grid; row: number; onChange: (next: Grid) => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={`Row ${row + 1} actions`} title={`Row ${row + 1} actions`}>
          <EllipsisVertical aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className={menuSurface}>
        <DropdownMenuItem onSelect={() => onChange(useRowAsHeader(grid, row))}>
          <Rows3 aria-hidden />
          Use as header
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => onChange(insertRow(grid, row))}>
          <ArrowUpToLine aria-hidden />
          Insert row above
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => onChange(insertRow(grid, row + 1))}>
          <ArrowDownToLine aria-hidden />
          Insert row below
        </DropdownMenuItem>
        <DropdownMenuItem variant="destructive" onSelect={() => onChange(deleteRow(grid, row))}>
          <Trash2 aria-hidden />
          Delete row
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function ColumnNameInput({
  grid,
  column,
  index,
  onChange,
}: {
  grid: Grid
  column: GridColumn
  index: number
  onChange: (next: Grid) => void
}) {
  return (
    <Input
      aria-label={`Column ${index + 1} name`}
      value={column.name}
      onChange={(e) => onChange(renameColumn(grid, index, e.target.value))}
      className={inputClass}
    />
  )
}

/**
 * The captured-table grid, as "Design rules > Grid editor" specs it. Holds no state of its own: every action calls
 * `onChange` with a new grid from `gridModel`.
 */
export function GridEditor({ grid, onChange, focus = null }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const focusedRef = useRef(false)

  // Scrolls a chart point's cell into view and focuses it, once. Retries each render until the cell exists (the
  // draft can still be initialising on the first paint) and then never again, so it doesn't steal focus back later.
  useEffect(() => {
    if (!focus || focusedRef.current) return
    const selector = `input[data-row-id="${focus.rowId}"][data-column-id="${focus.columnId}"]`
    const cell = containerRef.current?.querySelector<HTMLInputElement>(selector)
    if (!cell) return
    focusedRef.current = true
    cell.focus()
    cell.scrollIntoView({ block: 'center' })
  }, [focus, grid])

  return (
    <div className="flex flex-col gap-2">
      <div ref={containerRef} className="overflow-auto rounded-lg ring-1 ring-glass-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10" />
              {grid.columns.map((column, c) => (
                <TableHead key={column.key}>
                  <div className="flex items-center gap-1">
                    <ColumnNameInput grid={grid} column={column} index={c} onChange={onChange} />
                    <ColumnMenu grid={grid} column={c} onChange={onChange} />
                  </div>
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {grid.rows.map((row, r) => (
              <TableRow key={row.key}>
                <TableCell className="w-10">
                  <RowMenu grid={grid} row={r} onChange={onChange} />
                </TableCell>
                {row.cells.map((cell, c) => {
                  const edited = isEdited(cell)
                  return (
                    <TableCell key={grid.columns[c].key}>
                      <Input
                        aria-label={`Row ${r + 1}, column ${c + 1}`}
                        value={cell.raw}
                        data-row-id={row.id ?? undefined}
                        data-column-id={grid.columns[c].id ?? undefined}
                        data-edited={edited}
                        title={edited ? `Edited: extraction read “${cell.extracted}”` : undefined}
                        onChange={(e) => onChange(editCell(grid, r, c, e.target.value))}
                        className={cn(inputClass, edited && 'outline-1 outline-dashed outline-offset-1 outline-muted-foreground/60')}
                      />
                    </TableCell>
                  )
                })}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className="flex gap-2">
        <Button variant="ghost" size="sm" onClick={() => onChange(insertRow(grid, grid.rows.length))}>
          <Plus aria-hidden />
          Add row
        </Button>
        <Button variant="ghost" size="sm" onClick={() => onChange(insertColumn(grid, grid.columns.length))}>
          <Plus aria-hidden />
          Add column
        </Button>
      </div>
    </div>
  )
}
