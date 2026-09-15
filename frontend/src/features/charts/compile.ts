import type { ChartSpec, ResolvedData } from '@/api/client'
import { compileGridChart } from './compileGrid'
import { compileSeriesChart, type Compiled } from './compileSeries'
import type { ChartTheme } from './palette'

export type { Compiled }

/** The only way a chart spec becomes a Plotly figure. Pure: the same spec, data and theme give the same figure. */
export function compileChart(spec: ChartSpec, data: ResolvedData, theme: ChartTheme): Compiled {
  switch (spec.type) {
    case 'bar':
    case 'line':
    case 'scatter':
    case 'box':
    case 'scatter3d':
      return compileSeriesChart(spec, data, theme)
    default:
      return compileGridChart(spec, data, theme)
  }
}
