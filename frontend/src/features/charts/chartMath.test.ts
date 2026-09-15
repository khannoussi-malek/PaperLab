import { describe, expect, it } from 'vitest'
import { escapeText, fitLinear, symlog, symlogTicks } from './chartMath'

describe('fitLinear', () => {
  it('finds the least-squares line and its R²', () => {
    const fit = fitLinear([1, 2, 3, 4], [2, 4.1, 5.9, 8])
    expect(fit?.slope).toBeCloseTo(1.98, 5)
    expect(fit?.intercept).toBeCloseTo(0.05, 5)
    expect(fit?.r2).toBeCloseTo(0.9995, 3)
  })

  it('is exact on a perfect line, and has no line for fewer than two x values', () => {
    expect(fitLinear([0, 10], [1, 21])).toEqual({ slope: 2, intercept: 1, r2: 1 })
    expect(fitLinear([3], [3])).toBeNull()
    expect(fitLinear([5, 5, 5], [1, 2, 3])).toBeNull() // every x the same: no slope
  })

  it('gives R² 1 when every y is the same (the flat line explains them all)', () => {
    expect(fitLinear([1, 2, 3], [4, 4, 4])).toEqual({ slope: 0, intercept: 4, r2: 1 })
  })
})

describe('symlog', () => {
  it('keeps zero and the sign, and is logarithmic away from zero', () => {
    expect(symlog(0)).toBe(0)
    expect(symlog(9)).toBeCloseTo(1)
    expect(symlog(-99)).toBeCloseTo(-2)
  })

  it('ticks at 0 and powers of ten in the data range, labelled with the real values', () => {
    expect(symlogTicks(-150, 1200)).toEqual({
      tickvals: [symlog(-100), symlog(-10), symlog(-1), 0, symlog(1), symlog(10), symlog(100), symlog(1000)],
      ticktext: ['-100', '-10', '-1', '0', '1', '10', '100', '1,000'],
    })
    expect(symlogTicks(2, 50).ticktext).toEqual(['0', '1', '10'])
  })
})

describe('escapeText', () => {
  it("turns markup into literal text: Plotly reads <b>, <a href> and entities in labels, and labels come from PDFs and CSV files", () => {
    expect(escapeText('<a href="javascript:x">F1</a> & EM')).toBe('&lt;a href="javascript:x"&gt;F1&lt;/a&gt; &amp; EM')
  })
})
