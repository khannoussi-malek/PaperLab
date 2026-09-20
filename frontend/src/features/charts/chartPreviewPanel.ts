import type { PanelLimits } from '@/components/panelWidth'

/** The Charts page's preview column. Half the window at most: the list it sits beside is the page. */
export const CHART_PREVIEW: PanelLimits = {
  storageKey: 'paperlab-chart-preview-width',
  defaultWidth: 440,
  minWidth: 320,
  maxShare: 0.5,
}

/** Under this the axes crowd; over it the title and Open button fall below the fold. */
const MIN_CHART_HEIGHT = 200
const MAX_CHART_HEIGHT = 480
/** Roughly 3:2, the shape a chart reads best in. */
const CHART_ASPECT = 0.62

/** The drawing's height for a panel this wide, so widening the panel draws a bigger chart, not just more margin. */
export const previewChartHeight = (width: number): number =>
  Math.round(Math.min(MAX_CHART_HEIGHT, Math.max(MIN_CHART_HEIGHT, width * CHART_ASPECT)))
