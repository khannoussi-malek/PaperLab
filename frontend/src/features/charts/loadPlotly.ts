// Loaded on first use: Plotly is about 4.6 MB, and most views never draw a chart. A failed import (a flaky network, a
// blocked request, a stale-deploy chunk 404) clears the cache: a browser's module loader caches even a *failed*
// dynamic import for the page's lifetime, so a same-page retry of the identical specifier replays the same
// rejection instantly, without ever touching the network again. Clearing the cache doesn't undo that (only a real
// reload does — see PlotlyChart's Retry); it just keeps a stale rejection from haunting a future page
// load in the same browsing session.
let plotly: Promise<typeof import('plotly.js-dist-min')> | null = null
export function loadPlotly() {
  if (!plotly) {
    plotly = import('plotly.js-dist-min').catch((error: unknown) => {
      plotly = null
      throw error
    })
  }
  return plotly
}

/** Starts loading Plotly before a chart needs it. A failed warm-up is the chart's to retry and report, not ours. */
export function warmPlotly() {
  loadPlotly().catch(() => {})
}

/** A document listener: warms Plotly when the pointer or focus reaches a link into a chart, before the click. */
export function warmPlotlyAtChartLink(event: Event) {
  if (event.target instanceof Element && event.target.closest('a[href^="#/charts/"]')) warmPlotly()
}
