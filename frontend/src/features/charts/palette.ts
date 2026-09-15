import type { Layout } from 'plotly.js-dist-min'

export type ChartTheme = 'light' | 'dark'

/**
 * Series colours in a fixed order, never cycled. Checked with the dataviz palette validator on PaperLab's card surfaces
 * (#ffffff light, #1e293b dark): every neighbouring pair stays apart for colour-blind readers. Violet (AI) and red
 * (errors, delete) are left out. A few of them are under 3:1 against the surface, so every chart keeps a legend and a
 * data table view.
 */
export const SERIES_COLORS: Record<ChartTheme, readonly string[]> = {
  light: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300'],
  dark: ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300'],
}

/** One blue ramp for magnitude. Values near zero fade into the surface, so the dark theme runs it the other way. */
const BLUE_RAMP = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b']

export function sequentialScale(theme: ChartTheme): [number, string][] {
  const steps = theme === 'light' ? BLUE_RAMP : [...BLUE_RAMP].reverse()
  return steps.map((hex, i) => [i / (steps.length - 1), hex])
}

/** Text and chrome from the design tokens (MASTER.md): text never wears a series colour. */
export const CHART_INK: Record<ChartTheme, { text: string; muted: string; grid: string; surface: string }> = {
  light: { text: '#0f172a', muted: '#475569', grid: '#e2e8f0', surface: '#ffffff' },
  dark: { text: '#f1f5f9', muted: '#94a3b8', grid: 'rgba(255,255,255,0.1)', surface: '#1e293b' },
}

/** The series' own colour, or its slot in the fixed order. */
export function seriesColor(theme: ChartTheme, slot: number, own?: string | null): string {
  const colors = SERIES_COLORS[theme]
  return own ?? colors[Math.min(slot, colors.length - 1)]
}

const FONT = 'Atkinson Hyperlegible Next Variable, system-ui, sans-serif'

/** Hairline, recessive axes and grid; transparent backgrounds so the chart sits on its card. */
export function axisStyle(theme: ChartTheme) {
  const ink = CHART_INK[theme]
  return {
    color: ink.muted,
    gridcolor: ink.grid,
    linecolor: ink.grid,
    zeroline: false,
    automargin: true,
    tickfont: { color: ink.muted },
    title: { font: { color: ink.text } },
  } as const
}

export function baseLayout(theme: ChartTheme): Partial<Layout> {
  const ink = CHART_INK[theme]
  return {
    font: { family: FONT, size: 13, color: ink.text },
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    colorway: [...SERIES_COLORS[theme]],
    margin: { t: 32, r: 16, b: 48, l: 56 },
    hoverlabel: { bgcolor: ink.surface, bordercolor: ink.grid, font: { family: FONT, color: ink.text } },
    legend: { orientation: 'h', x: 0, y: 1.02, yanchor: 'bottom', font: { color: ink.text } },
    barcornerradius: 4,
    bargap: 0.35,
    xaxis: axisStyle(theme),
    yaxis: axisStyle(theme),
  }
}
