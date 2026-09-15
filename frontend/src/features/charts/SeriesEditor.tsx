import { Trash2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import type { Dataset, SeriesChartSpec, SeriesSpec } from '@/api/client'
import { useLoadDataset } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { columnInfo, newSeries, type ColumnInfo } from './builderSpec'
import { DataButton, DataPicker } from './DataPicker'
import { SERIES_COLORS } from './palette'
import { useChartTheme } from './useChartTheme'

export function Field({ id, label, children }: { id: string; label: ReactNode; children: ReactNode }) {
  return (
    <div className="grid min-w-0 gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  )
}

type Option = { value: string; label: string; samples?: string[]; disabled?: boolean }

const NONE = 'none'

/**
 * A labelled shadcn `Select`: any `extra` items (a "None" item has the value `'none'`, which a `null` value selects),
 * then columns, each showing its sample values in muted text.
 */
export function LabelledSelect({
  id,
  label,
  value,
  columns = [],
  extra = [],
  onChange,
}: {
  id: string
  label: string
  value: string | null
  columns?: ColumnInfo[]
  extra?: Option[]
  onChange: (value: string) => void
}) {
  const options: Option[] = [...extra, ...columns.map((c) => ({ value: c.id, label: c.name, samples: c.samples }))]
  return (
    <Field id={id} label={label}>
      <Select value={value ?? NONE} onValueChange={onChange}>
        <SelectTrigger id={id} className="w-full">
          {/* The chosen item's name only; its samples show in the list. */}
          <SelectValue placeholder="Choose…">{options.find((option) => option.value === (value ?? NONE))?.label}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value} disabled={option.disabled}>
              <span className="truncate">{option.label}</span>
              {option.samples && option.samples.length > 0 && (
                <span className="truncate text-muted-foreground">{option.samples.join(', ')}</span>
              )}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  )
}

type Props = {
  series: SeriesSpec
  index: number
  dataset: Dataset | undefined
  /** The chart's type: Z shows for 3D, the trend line for line and scatter. */
  type: SeriesChartSpec['type']
  onChange: (series: SeriesSpec) => void
  onRemove: () => void
  /** Small multiples: every series draws in its own panel, in the first colour unless it has its own. */
  facet: boolean
}

/** One series of a bar, line, scatter, box or 3D chart: its data, columns, rows, colour, trend and scale. */
export function SeriesEditor({ series, index, dataset, type, onChange, onRemove, facet }: Props) {
  const theme = useChartTheme()
  const [picking, setPicking] = useState(false)
  const [multiply, setMultiply] = useState(String(series.multiply))
  const loadDataset = useLoadDataset()
  const [pickError, setPickError] = useState<string | null>(null)

  async function pickData(datasetId: string) {
    setPickError(null)
    try {
      const next = await loadDataset(datasetId)
      const fresh = newSeries(next, [])
      if (!fresh) return setPickError(`“${next.name}” has no number columns to chart.`)
      onChange({ ...fresh, id: series.id, name: series.name, color: series.color, multiply: series.multiply })
    } catch (error) {
      setPickError(error instanceof Error ? error.message : String(error))
    }
  }
  const columns = dataset ? columnInfo(dataset) : []
  // "Y" and "X" list number columns first.
  const numbersFirst = [...columns.filter((c) => c.numeric), ...columns.filter((c) => !c.numeric)]
  const numbers = columns.filter((c) => c.numeric)
  const set = (patch: Partial<SeriesSpec>) => onChange({ ...series, ...patch })
  const key = `series-${series.id}`
  const n = index + 1
  const autoSlot = facet ? 1 : Math.min(index, 5) + 1
  const y = columns.find((c) => c.id === series.y)

  return (
    <section className="series-card flex min-w-0 flex-col gap-3 rounded-xl bg-glass-strong p-3 ring-1 ring-glass-border" aria-label={`Series ${n}`}>
      <div className="flex items-end gap-2">
        <div className="min-w-0 flex-1">
          <Field id={`${key}-name`} label={`Series ${n}`}>
            <Input
              id={`${key}-name`}
              value={series.name}
              maxLength={200}
              placeholder={y?.name ?? 'Name'}
              onChange={(e) => set({ name: e.target.value })}
            />
          </Field>
        </div>
        <Button variant="ghost" size="icon" aria-label="Remove series" className="text-muted-foreground" onClick={onRemove}>
          <Trash2 aria-hidden />
        </Button>
      </div>

      <DataButton id={`${key}-data`} name={dataset?.name} onClick={() => setPicking(true)} />
      {pickError && (
        <p className="text-xs text-destructive" role="alert">
          {pickError}
        </p>
      )}
      <DataPicker open={picking} onOpenChange={setPicking} onPick={(datasetId) => void pickData(datasetId)} />

      <div className="grid grid-cols-2 gap-3">
        <LabelledSelect
          id={`${key}-x`}
          label="X"
          value={series.x ?? null}
          columns={type === 'scatter3d' ? numbers : numbersFirst}
          extra={[{ value: NONE, label: 'Row order' }]}
          onChange={(x) => set({ x: x === NONE ? null : x })}
        />
        <LabelledSelect id={`${key}-y`} label="Y" value={series.y} columns={numbersFirst} onChange={(next) => set({ y: next })} />
        {type === 'scatter3d' && (
          <LabelledSelect id={`${key}-z`} label="Z" value={series.z ?? null} columns={numbers} onChange={(z) => set({ z })} />
        )}
      </div>
      <LabelledSelect
        id={`${key}-error`}
        label="Error bars"
        value={series.error}
        columns={numbers.filter((c) => c.id !== series.y)}
        extra={[
          { value: NONE, label: 'None' },
          { value: 'cells', label: 'From the cells (± in the text)', disabled: !y?.hasErrors },
        ]}
        onChange={(error) => set({ error })}
      />

      {dataset && <RowPicker series={series} dataset={dataset} onChange={(rows) => set({ rows })} />}

      <fieldset className="grid gap-1.5">
        <legend className="mb-1.5 text-sm font-medium">
          Colour <span className="font-normal text-muted-foreground">{series.color ? '' : `(automatic: Colour ${autoSlot})`}</span>
        </legend>
        <div className="flex gap-1.5">
          {SERIES_COLORS.light.map((light, i) => {
            const pressed = series.color === light || series.color === SERIES_COLORS.dark[i]
            return (
              <button
                key={light}
                type="button"
                aria-label={`Colour ${i + 1}`}
                aria-pressed={pressed}
                // ponytail: stores the light hex, which the dark theme draws as is; store a slot if the two drift apart.
                onClick={() => set({ color: pressed ? null : light })}
                className={cn(
                  'size-6 cursor-pointer rounded-full ring-offset-2 ring-offset-background outline-none focus-visible:ring-3 focus-visible:ring-ring/50',
                  pressed && 'ring-2 ring-foreground',
                )}
                style={{ backgroundColor: SERIES_COLORS[theme][i] }}
              />
            )
          })}
        </div>
      </fieldset>

      <div className="grid grid-cols-2 gap-3">
        {(type === 'line' || type === 'scatter') && (
          <LabelledSelect
            id={`${key}-trend`}
            label="Trend line"
            value={series.trend}
            extra={[
              { value: NONE, label: 'None' },
              { value: 'linear', label: 'Linear' },
            ]}
            onChange={(trend) => set({ trend: trend === 'linear' ? 'linear' : 'none' })}
          />
        )}
        <Field id={`${key}-multiply`} label="Multiply by">
          <Input
            id={`${key}-multiply`}
            type="number"
            step="any"
            value={multiply}
            onChange={(e) => {
              setMultiply(e.target.value)
              const factor = Number(e.target.value)
              // Blank or 0 would erase the series; keep the last factor until a usable one is typed.
              if (e.target.value.trim() !== '' && Number.isFinite(factor) && factor !== 0) set({ multiply: factor })
            }}
          />
        </Field>
      </div>
    </section>
  )
}

/** "Rows": which rows the series draws, all by default. The last ticked row can't be unticked. */
function RowPicker({ series, dataset, onChange }: { series: SeriesSpec; dataset: Dataset; onChange: (rows: string[] | null) => void }) {
  const chosen = series.rows ?? dataset.rows.map((row) => row.id)
  const label = (row: Dataset['rows'][number], r: number) =>
    row.cells.find((cell) => cell.column_id === series.x)?.raw || `Row ${r + 1}`

  function toggle(rowId: string, on: boolean) {
    const next = dataset.rows.map((row) => row.id).filter((id) => (id === rowId ? on : chosen.includes(id)))
    if (next.length > 0) onChange(next.length === dataset.rows.length ? null : next)
  }

  return (
    <details className="group text-sm">
      <summary className="cursor-pointer font-medium">
        Rows{' '}
        <span className="font-normal text-muted-foreground tabular-nums">
          {series.rows ? `${chosen.length} of ${dataset.rows.length}` : 'all'}
        </span>
      </summary>
      <ul className="mt-2 grid max-h-48 gap-1.5 overflow-y-auto">
        {dataset.rows.map((row, r) => {
          const id = `series-${series.id}-row-${row.id}`
          return (
            <li key={row.id} className="flex items-center gap-2">
              <Checkbox id={id} checked={chosen.includes(row.id)} onCheckedChange={(on) => toggle(row.id, on === true)} />
              <Label htmlFor={id} className="truncate font-normal">
                {label(row, r)}
              </Label>
            </li>
          )
        })}
      </ul>
    </details>
  )
}
