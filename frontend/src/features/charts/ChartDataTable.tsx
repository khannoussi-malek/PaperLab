import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { ChartTableView } from './chartTable'

/** A chart's numbers as a plain, screen-reader-friendly table: the accessible version of the plot. */
export function ChartDataTable({ view }: { view: ChartTableView }) {
  return (
    <div className="overflow-auto">
      <Table aria-label="Chart data">
        <TableHeader>
          <TableRow>
            {view.columns.map((column, i) => (
              <TableHead key={i}>{column}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {view.rows.map((row, r) => (
            <TableRow key={r}>
              {row.map((cell, c) => (
                <TableCell key={c}>{cell}</TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
