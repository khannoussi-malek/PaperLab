import type { ChartSpec, Dataset } from '@/api/client'
import { delayedIn } from '@/components/motion'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { columnInfo, type ColumnInfo } from './builderSpec'
import { LabelledSelect } from './SeriesEditor'

type GridSpec = Exclude<ChartSpec, { series: unknown }>

type Props = {
  spec: GridSpec
  dataset: Dataset | undefined
  onChange: (spec: GridSpec) => void
}

/** A checkbox per column; the ticked ones keep the dataset's column order. */
function ColumnChecklist({ legend, columns, chosen, onChange }: { legend: string; columns: ColumnInfo[]; chosen: string[]; onChange: (ids: string[]) => void }) {
  return (
    <fieldset className="grid gap-1.5">
      <legend className="mb-1.5 text-sm font-medium">{legend}</legend>
      <ul className="grid max-h-48 gap-1.5 overflow-y-auto">
        {columns.map((column) => {
          const id = `grid-${legend}-${column.id}`
          return (
            <li key={column.id} className="flex items-center gap-2">
              <Checkbox
                id={id}
                checked={chosen.includes(column.id)}
                onCheckedChange={(on) =>
                  onChange(columns.map((c) => c.id).filter((c) => (c === column.id ? on === true : chosen.includes(c))))
                }
              />
              <Label htmlFor={id} className="min-w-0 font-normal">
                <span className="truncate">{column.name}</span>
                <span className="truncate text-muted-foreground">{column.samples.join(', ')}</span>
              </Label>
            </li>
          )
        })}
      </ul>
    </fieldset>
  )
}

/** The column pickers of a heatmap, surface, contour or parallel coordinates chart. */
export function GridChartFields({ spec, dataset, onChange }: Props) {
  if (!dataset) return <p className={cn('text-sm text-muted-foreground', delayedIn)}>Loading the data…</p>
  const columns = columnInfo(dataset)
  const numbers = columns.filter((c) => c.numeric)

  if (spec.type === 'heatmap') {
    return (
      <>
        <LabelledSelect id="grid-row-labels" label="Row labels" value={spec.row_labels} columns={columns} onChange={(row_labels) => onChange({ ...spec, row_labels })} />
        <ColumnChecklist legend="Columns" columns={numbers} chosen={spec.columns} onChange={(ids) => onChange({ ...spec, columns: ids })} />
      </>
    )
  }
  if (spec.type === 'parcoords') {
    return (
      <>
        <ColumnChecklist legend="Axes" columns={numbers} chosen={spec.dimensions} onChange={(ids) => onChange({ ...spec, dimensions: ids })} />
        <LabelledSelect
          id="grid-color-by"
          label="Colour by"
          value={spec.color_by ?? null}
          columns={numbers}
          extra={[{ value: 'none', label: 'None' }]}
          onChange={(value) => onChange({ ...spec, color_by: value === 'none' ? null : value })}
        />
      </>
    )
  }
  return (
    <div className="grid grid-cols-3 gap-3">
      {(['x', 'y', 'z'] as const).map((axis) => (
        <LabelledSelect
          key={axis}
          id={`grid-${axis}`}
          label={axis.toUpperCase()}
          value={spec[axis]}
          columns={numbers}
          onChange={(value) => onChange({ ...spec, [axis]: value })}
        />
      ))}
    </div>
  )
}
