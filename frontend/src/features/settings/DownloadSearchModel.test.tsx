// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { DownloadSearchModel } from './DownloadSearchModel'

vi.mock('@/api/queries', () => ({ useEmbeddingStatus: () => ({ data: { model_present: false, download_bytes: 138_000_000 } }) }))
vi.mock('./useSearchModelDownload', () => ({ useSearchModelDownload: () => ({ state: { status: 'downloading', completed: 50, total: 100 }, start: vi.fn() }) }))
vi.mock('@/features/graph/viewModel', () => ({ hasWebGL: () => false }))
vi.stubGlobal('matchMedia', () => ({ matches: false }))

test('with the scene asked for but no WebGL, the status line and progress bar are exactly as before', () => {
  render(<DownloadSearchModel alwaysShowStatus scene />)
  expect(screen.getByRole('progressbar', { name: 'Downloading the search model' })).toBeInTheDocument()
  expect(document.querySelector('.search-model-status')).not.toBeNull()
  expect(document.querySelector('canvas')).toBeNull()
})
