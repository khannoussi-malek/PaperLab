// @vitest-environment jsdom
import { render, screen, fireEvent } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import type { Hit } from '@/api/client'
import { HitContextMenu, HitMenu } from './HitMenu'

const hit: Hit = {
  id: 'h1',
  run_id: 'run-1',
  external_ref_id: null,
  source_method: 'arxiv',
  normalized_title: 'a paper about llms',
  first_seen_at: '2026-09-24T00:00:00Z',
  stage1_status: null,
  stage1_exclude_reason: null,
  stage1_note: null,
  priority: null,
  topic_fit: null,
  acquisition_status: 'pending',
  paper_id: null,
  sources: [],
}

test('the ⋮ menu offers Relevant, Maybe, Not relevant… and Snowball', async () => {
  render(<HitMenu hit={hit} onReview={vi.fn()} onSnowball={vi.fn()} />)
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Hit actions' }))

  expect(await screen.findByRole('menuitem', { name: 'Relevant' })).toBeInTheDocument()
  expect(screen.getByRole('menuitem', { name: 'Maybe' })).toBeInTheDocument()
  expect(screen.getByRole('menuitem', { name: 'Not relevant…' })).toBeInTheDocument()
  expect(screen.getByRole('menuitem', { name: 'Snowball' })).toBeInTheDocument()
})

test('clicking Snowball in the ⋮ menu calls onSnowball with the hit id, not onReview', async () => {
  const onReview = vi.fn()
  const onSnowball = vi.fn()
  render(<HitMenu hit={hit} onReview={onReview} onSnowball={onSnowball} />)
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Hit actions' }))

  fireEvent.click(await screen.findByRole('menuitem', { name: 'Snowball' }))

  expect(onSnowball).toHaveBeenCalledWith('h1')
  expect(onReview).not.toHaveBeenCalled()
})

test('the right-click menu also offers Snowball and calls onSnowball with the hit id', async () => {
  const onSnowball = vi.fn()
  render(
    <HitContextMenu hit={hit} onReview={vi.fn()} onSnowball={onSnowball}>
      <div>row</div>
    </HitContextMenu>,
  )
  fireEvent.contextMenu(screen.getByText('row'))

  fireEvent.click(await screen.findByRole('menuitem', { name: 'Snowball' }))

  expect(onSnowball).toHaveBeenCalledWith('h1')
})
