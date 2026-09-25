import { describe, expect, it } from 'vitest'
import { downloadAnnouncement, downloadLabel, refusedDownload, showSearchNotice, statusLine } from './searchModel'

describe('statusLine', () => {
  it('says whether the search model is here, and how far a download has got', () => {
    expect(statusLine(false, { status: 'idle' })).toBe('Search model: not downloaded')
    expect(statusLine(false, { status: 'downloading', completed: 58_000_000, total: 138_007_688 })).toBe(
      'Search model: downloading… 42%',
    )
    expect(statusLine(false, { status: 'downloading', completed: 0, total: 0 })).toBe('Search model: downloading… 0%')
    expect(statusLine(true, { status: 'idle' })).toBe('Search model: ready')
    expect(statusLine(false, { status: 'done', papersQueued: 3 })).toBe('Search model: ready')
  })

  it('is back to not downloaded after a failed download', () => {
    expect(statusLine(false, { status: 'error', message: 'The disk is full.' })).toBe('Search model: not downloaded')
  })
})

describe('downloadLabel', () => {
  it('names the size in whole decimal megabytes, whichever variant ships', () => {
    expect(downloadLabel(137_296_292 + 711_396)).toBe('Download search model · 138 MB') // int8 + tokenizer
    expect(downloadLabel(547_310_275 + 711_396)).toBe('Download search model · 548 MB') // full precision + tokenizer
    expect(downloadLabel(137_296_292)).toBe('Download search model · 137 MB')
  })
})

describe('refusedDownload', () => {
  it('reads a model already here as done, and another download as an error in words', () => {
    expect(refusedDownload('model_present')).toEqual({ status: 'done', papersQueued: 0 })
    expect(refusedDownload('download_running')).toEqual({
      status: 'error',
      message: 'The search model is already downloading in another window.',
    })
    expect(refusedDownload('Internal Server Error')).toEqual({ status: 'error', message: 'Internal Server Error' })
  })
})

describe('downloadAnnouncement', () => {
  it('says the download finished, and nothing otherwise: errors already announce through their own Alert', () => {
    expect(downloadAnnouncement({ status: 'done', papersQueued: 3 })).toBe('Search model downloaded.')
    expect(downloadAnnouncement({ status: 'idle' })).toBe('')
    expect(downloadAnnouncement({ status: 'downloading', completed: 0, total: 0 })).toBe('')
    expect(downloadAnnouncement({ status: 'error', message: 'The disk is full.' })).toBe('')
  })
})

describe('showSearchNotice', () => {
  const builtIn = { kind: 'builtin' as const }

  it('shows only while Built-in is the source, its model is missing, and some paper is too long to chat with whole', () => {
    expect(showSearchNotice({ source: builtIn, model_present: false, papers_needing_search: 2 })).toBe(true)
    expect(showSearchNotice({ source: builtIn, model_present: true, papers_needing_search: 2 })).toBe(false)
    expect(showSearchNotice({ source: builtIn, model_present: false, papers_needing_search: 0 })).toBe(false)
    // Another source searches without the built-in model: there is nothing to download (D133).
    expect(showSearchNotice({ source: { kind: 'openai' }, model_present: false, papers_needing_search: 2 })).toBe(false)
  })
})
