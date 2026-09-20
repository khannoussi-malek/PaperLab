import { describe, expect, it } from 'vitest'
import { activeNav, activeWorkspaceId, railItem } from './nav'
import type { Route } from '@/lib/route'

describe('activeNav', () => {
  it('lights up the rail item for each top-level view', () => {
    expect(activeNav({ name: 'library' })).toBe('library')
    expect(activeNav({ name: 'graph' })).toBe('graph')
    expect(activeNav({ name: 'charts' })).toBe('charts')
    expect(activeNav({ name: 'settings', section: 'models' })).toBe('settings')
    expect(activeNav({ name: 'connect-claude' })).toBe('connect-claude')
    expect(activeNav({ name: 'workspace', workspaceId: 'w1', tab: 'papers' })).toBe('workspace')
  })

  it('keeps Charts lit while you are inside a chart, the builder or a dataset', () => {
    expect(activeNav({ name: 'chart', chartId: 'c1' })).toBe('charts')
    expect(activeNav({ name: 'chart-builder', chartId: 'c1', datasetId: null })).toBe('charts')
    expect(activeNav({ name: 'dataset', datasetId: 'd1', focus: null })).toBe('charts')
  })

  it('lights up nothing in the two views that draw no rail', () => {
    const reader: Route = { name: 'reader', paperId: 'p1', tab: 'notes', target: null }
    expect(activeNav(reader)).toBeNull()
    expect(activeNav({ name: 'setup' })).toBeNull()
  })
})

describe('activeWorkspaceId', () => {
  it('is the open workspace, and null everywhere else', () => {
    expect(activeWorkspaceId({ name: 'workspace', workspaceId: 'w1', tab: 'notes' })).toBe('w1')
    expect(activeWorkspaceId({ name: 'library' })).toBeNull()
    expect(activeWorkspaceId({ name: 'charts' })).toBeNull()
  })
})

describe('railItem', () => {
  it('marks the current row with more than colour: a left bar and a heavier weight', () => {
    expect(railItem(true)).toContain('inset_3px_0_0')
    expect(railItem(true)).toContain('font-medium')
    expect(railItem(false)).not.toContain('inset_3px_0_0')
  })
})
