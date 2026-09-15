import type { ChartSpec } from '@/api/client'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { LabelledSelect, Field } from './SeriesEditor'

type Axis = NonNullable<NonNullable<ChartSpec['axes']>['x']>
type Layout = NonNullable<ChartSpec['layout']>

const SCALES: { value: Axis['scale']; label: string }[] = [
  { value: 'linear', label: 'Linear' },
  { value: 'log', label: 'Log' },
  { value: 'symlog', label: 'Symmetric log' },
  { value: 'category', label: 'Categories' },
]

/** "Axes" (labels and the y scale) and "Layout" (bar mode, small multiples) of a chart. */
export function AxesFields({ spec, onChange }: { spec: ChartSpec; onChange: (spec: ChartSpec) => void }) {
  const axis = (key: 'x' | 'y'): Axis => ({ label: '', scale: 'linear', ...spec.axes?.[key] })
  const setAxis = (key: 'x' | 'y', patch: Partial<Axis>) => onChange({ ...spec, axes: { ...spec.axes, [key]: { ...axis(key), ...patch } } })
  const layout: Layout = { barmode: 'group', facet: 'none', facet_columns: 2, ...spec.layout }
  const setLayout = (patch: Partial<Layout>) => onChange({ ...spec, layout: { ...layout, ...patch } })
  const facets = 'series' in spec && spec.type !== 'scatter3d'

  return (
    <>
      <section className="grid gap-3">
        <h2 className="text-sm font-medium">Axes</h2>
        <div className="grid grid-cols-2 gap-3">
          <Field id="axis-x-label" label="X axis label">
            <Input id="axis-x-label" value={axis('x').label} onChange={(e) => setAxis('x', { label: e.target.value })} />
          </Field>
          <Field id="axis-y-label" label="Y axis label">
            <Input id="axis-y-label" value={axis('y').label} onChange={(e) => setAxis('y', { label: e.target.value })} />
          </Field>
        </div>
        <LabelledSelect
          id="axis-y-scale"
          label="Y axis scale"
          value={axis('y').scale}
          extra={SCALES}
          onChange={(scale) => setAxis('y', { scale: scale as Axis['scale'] })}
        />
      </section>

      {(spec.type === 'bar' || facets) && (
        <section className="grid gap-3">
          <h2 className="text-sm font-medium">Layout</h2>
          {spec.type === 'bar' && (
            <LabelledSelect
              id="layout-barmode"
              label="Bar mode"
              value={layout.barmode}
              extra={[
                { value: 'group', label: 'Grouped' },
                { value: 'stack', label: 'Stacked' },
              ]}
              onChange={(barmode) => setLayout({ barmode: barmode === 'stack' ? 'stack' : 'group' })}
            />
          )}
          {facets && (
            <div className="flex items-center gap-2">
              <Checkbox
                id="layout-facet"
                checked={layout.facet === 'series'}
                onCheckedChange={(on) => setLayout({ facet: on === true ? 'series' : 'none' })}
              />
              <Label htmlFor="layout-facet">Small multiples</Label>
            </div>
          )}
        </section>
      )}
    </>
  )
}
