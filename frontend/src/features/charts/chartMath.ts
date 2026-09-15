export type LinearFit = { slope: number; intercept: number; r2: number }

/** Least-squares line through the points, with R². Null without two distinct x values. Plotly.js has no trend lines. */
export function fitLinear(xs: number[], ys: number[]): LinearFit | null {
  const n = xs.length
  if (n < 2) return null
  const meanX = xs.reduce((a, b) => a + b, 0) / n
  const meanY = ys.reduce((a, b) => a + b, 0) / n
  let sxx = 0
  let sxy = 0
  let syy = 0
  xs.forEach((x, i) => {
    sxx += (x - meanX) ** 2
    sxy += (x - meanX) * (ys[i] - meanY)
    syy += (ys[i] - meanY) ** 2
  })
  if (sxx === 0) return null
  const slope = sxy / sxx
  const intercept = meanY - slope * meanX
  // All y equal: the flat line fits them exactly.
  const r2 = syy === 0 ? 1 : (sxy * sxy) / (sxx * syy)
  return { slope, intercept, r2 }
}

/** A log scale that keeps zero and negative values: sign(v) · log10(1 + |v|). Plotly has no such axis type. */
export const symlog = (value: number): number => Math.sign(value) * Math.log10(1 + Math.abs(value))

const formatTick = new Intl.NumberFormat('en-US', { maximumFractionDigits: 6 })

/** Ticks for a symlog axis: 0 and ±powers of ten reaching the data, placed on the transformed scale, labelled with the
 * values a reader knows. */
export function symlogTicks(min: number, max: number): { tickvals: number[]; ticktext: string[] } {
  const values = [0]
  for (let step = 1; step <= Math.max(-min, max); step *= 10) {
    if (max >= step) values.push(step)
    if (-min >= step) values.unshift(-step)
  }
  return { tickvals: values.map(symlog), ticktext: values.map((v) => formatTick.format(v)) }
}

/** Plotly renders a small HTML subset (<b>, <br>, <a href>) and entities in every text it draws. Names and labels
 * come from PDFs, CSV headers and typing, so they are escaped into literal text first. */
export const escapeText = (text: string): string => text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
