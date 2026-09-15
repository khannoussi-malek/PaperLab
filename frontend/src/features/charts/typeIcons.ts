import { Box, ChartCandlestick, ChartColumn, ChartLine, ChartNoAxesColumn, ChartScatter, Grid3x3, Waves } from 'lucide-react'
import type { ChartSpec } from '@/api/client'

/** Each chart type's icon, in the Charts list and the builder's type picker. */
export const TYPE_ICON: Record<ChartSpec['type'], typeof ChartColumn> = {
  bar: ChartColumn,
  line: ChartLine,
  scatter: ChartScatter,
  box: ChartCandlestick,
  heatmap: Grid3x3,
  scatter3d: Box,
  surface: Box,
  contour: Waves,
  parcoords: ChartNoAxesColumn,
}
