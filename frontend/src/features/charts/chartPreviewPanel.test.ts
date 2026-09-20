import { describe, expect, it } from 'vitest'
import { maxPanelWidth } from '@/components/panelWidth'
import { CHART_PREVIEW, previewChartHeight } from './chartPreviewPanel'

describe('CHART_PREVIEW', () => {
  it('starts wider than the list preview it replaced, and never takes more than half the window', () => {
    expect(CHART_PREVIEW.defaultWidth).toBeGreaterThan(352) // the old fixed 22rem
    expect(maxPanelWidth(CHART_PREVIEW, 1280)).toBe(640)
  })

  it('remembers its width under a key of its own, not the reader’s', () => {
    expect(CHART_PREVIEW.storageKey).not.toBe('paperlab-panel-width')
  })
})

describe('previewChartHeight', () => {
  it('grows with the panel, so a wider preview draws a bigger chart', () => {
    expect(previewChartHeight(600)).toBeGreaterThan(previewChartHeight(400))
  })

  it('stays between a readable floor and a ceiling, so the details below stay in view', () => {
    expect(previewChartHeight(CHART_PREVIEW.minWidth)).toBe(200)
    expect(previewChartHeight(100)).toBe(200)
    expect(previewChartHeight(5000)).toBe(480)
  })

  it('is a whole number of pixels', () => {
    expect(previewChartHeight(433)).toBe(Math.round(previewChartHeight(433)))
  })
})
