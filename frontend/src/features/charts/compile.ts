import type { ChartSpec, ResolvedData } from '@/api/client'
import { compileSeriesChart, type Compiled } from './compileSeries'
import type { ChartTheme } from './palette'

export type { Compiled }

export function compileChart(spec: ChartSpec, data: ResolvedData, theme: ChartTheme): Compiled {
  if ('series' in spec) return compileSeriesChart(spec, data, theme)
  return { traces: [], layout: {}, warnings: [], seriesCount: 0 }
}
