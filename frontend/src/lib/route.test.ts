import { describe, expect, it } from 'vitest'
import {
  chartHref,
  chartsHref,
  chunkHref,
  datasetHref,
  editChartHref,
  newChartHref,
  noteHref,
  parseRoute,
  readerHref,
  regionHref,
  settingsHref,
  workspaceHref,
} from './route'

const id = '1f0e7570-3249-4d59-aa5c-8f9a03c2b70a'
const other = '9b2d4c1e-7f3a-4e55-8c21-0d6b5a4f3e21'

describe('parseRoute', () => {
  it('opens the reader for a paper id, on the Notes tab by default', () => {
    expect(parseRoute(readerHref(id))).toEqual({ name: 'reader', paperId: id, tab: 'notes', target: null })
  })

  it('keeps the Chat tab in the hash', () => {
    expect(readerHref(id, 'chat')).toBe(`#/papers/${id}?tab=chat`)
    expect(parseRoute(readerHref(id, 'chat'))).toEqual({ name: 'reader', paperId: id, tab: 'chat', target: null })
  })

  it('treats an unknown tab as Notes', () => {
    expect(parseRoute(`#/papers/${id}?tab=graph`)).toEqual({ name: 'reader', paperId: id, tab: 'notes', target: null })
  })

  it('reads a chunk target with its page, for the reader to flash once', () => {
    expect(chunkHref(id, other, 3)).toBe(`#/papers/${id}?chunk=${other}&page=3`)
    expect(parseRoute(chunkHref(id, other, 3))).toEqual({
      name: 'reader',
      paperId: id,
      tab: 'notes',
      target: { kind: 'chunk', id: other, page: 3 },
    })
  })

  it('reads a note target, for the reader to focus once', () => {
    expect(noteHref(id, other)).toBe(`#/papers/${id}?note=${other}`)
    expect(parseRoute(noteHref(id, other))).toEqual({
      name: 'reader',
      paperId: id,
      tab: 'notes',
      target: { kind: 'note', id: other },
    })
  })

  it('ignores a target with a malformed id, or a chunk without a page', () => {
    const reader = { name: 'reader', paperId: id, tab: 'notes', target: null }
    expect(parseRoute(`#/papers/${id}?note=not-an-id`)).toEqual(reader)
    expect(parseRoute(`#/papers/${id}?chunk=${other}`)).toEqual(reader)
    expect(parseRoute(`#/papers/${id}?chunk=${other}&page=0`)).toEqual(reader)
  })

  it('opens a workspace on its Papers tab by default, and keeps another tab in the hash', () => {
    expect(workspaceHref(id)).toBe(`#/workspaces/${id}`)
    expect(parseRoute(workspaceHref(id))).toEqual({ name: 'workspace', workspaceId: id, tab: 'papers' })
    expect(workspaceHref(id, 'chat')).toBe(`#/workspaces/${id}?tab=chat`)
    expect(parseRoute(workspaceHref(id, 'notes'))).toEqual({ name: 'workspace', workspaceId: id, tab: 'notes' })
    expect(parseRoute(`#/workspaces/${id}?tab=graph`)).toEqual({ name: 'workspace', workspaceId: id, tab: 'papers' })
  })

  it('keeps the Data tab in the hash', () => {
    expect(readerHref(id, 'data')).toBe(`#/papers/${id}?tab=data`)
    expect(parseRoute(readerHref(id, 'data'))).toEqual({ name: 'reader', paperId: id, tab: 'data', target: null })
  })

  it('reads a region target (a page and its rects) for the reader to flash once, on the Data tab', () => {
    const rects: [number, number, number, number][] = [
      [72, 100, 90, 110.5],
      [72, 112, 90, 122],
    ]
    expect(regionHref(id, 7, rects)).toBe(`#/papers/${id}?tab=data&page=7&rects=72,100,90,110.5;72,112,90,122`)
    expect(parseRoute(regionHref(id, 7, rects))).toEqual({
      name: 'reader',
      paperId: id,
      tab: 'data',
      target: { kind: 'region', id: '7:72,100,90,110.5;72,112,90,122', page: 7, rects },
    })
  })

  it('ignores a region target with a malformed rect or no page', () => {
    const data = { name: 'reader', paperId: id, tab: 'data', target: null }
    expect(parseRoute(`#/papers/${id}?tab=data&page=7&rects=72,100,90`)).toEqual(data)
    expect(parseRoute(`#/papers/${id}?tab=data&page=7&rects=72,100,x,110`)).toEqual(data)
    expect(parseRoute(`#/papers/${id}?tab=data&rects=72,100,90,110`)).toEqual(data)
  })

  it('opens the charts page, a chart, the chart builder (new or editing) and a dataset', () => {
    expect([chartsHref, chartHref(id), editChartHref(id), newChartHref(), newChartHref(other), datasetHref(other)]).toEqual([
      '#/charts',
      `#/charts/${id}`,
      `#/charts/${id}/edit`,
      '#/charts/new',
      `#/charts/new?dataset=${other}`,
      `#/datasets/${other}`,
    ])
    expect(parseRoute(chartsHref)).toEqual({ name: 'charts' })
    expect(parseRoute(chartHref(id))).toEqual({ name: 'chart', chartId: id })
    expect(parseRoute(editChartHref(id))).toEqual({ name: 'chart-builder', chartId: id, datasetId: null })
    expect(parseRoute(newChartHref())).toEqual({ name: 'chart-builder', chartId: null, datasetId: null })
    expect(parseRoute(newChartHref(other))).toEqual({ name: 'chart-builder', chartId: null, datasetId: other })
    expect(parseRoute(`#/charts/new?dataset=nope`)).toEqual({ name: 'chart-builder', chartId: null, datasetId: null })
    expect(parseRoute(datasetHref(other))).toEqual({ name: 'dataset', datasetId: other, focus: null })
  })

  it('falls back to the library for anything else', () => {
    expect(parseRoute('')).toEqual({ name: 'library' })
    expect(parseRoute('#/')).toEqual({ name: 'library' })
    expect(parseRoute('#/papers/not-an-id')).toEqual({ name: 'library' })
    expect(parseRoute('#/workspaces/not-an-id')).toEqual({ name: 'library' })
    expect(parseRoute('#/charts/not-an-id')).toEqual({ name: 'library' })
    expect(parseRoute('#/datasets/not-an-id')).toEqual({ name: 'library' })
  })

  it('opens a dataset focused on one cell, and ignores a half or broken focus', () => {
    const focus = { rowId: id, columnId: other }
    expect(datasetHref(other, focus)).toBe(`#/datasets/${other}?row=${id}&column=${other}`)
    expect(parseRoute(datasetHref(other, focus))).toEqual({ name: 'dataset', datasetId: other, focus })
    expect(parseRoute(`#/datasets/${other}?row=${id}`)).toEqual({ name: 'dataset', datasetId: other, focus: null })
    expect(parseRoute(`#/datasets/${other}?row=nope&column=${other}`)).toEqual({ name: 'dataset', datasetId: other, focus: null })
  })

  it('opens the settings page, and nothing under it', () => {
    expect(settingsHref).toBe('#/settings')
    expect(parseRoute(settingsHref)).toEqual({ name: 'settings' })
    expect(parseRoute('#/settings/models')).toEqual({ name: 'library' })
  })
})
