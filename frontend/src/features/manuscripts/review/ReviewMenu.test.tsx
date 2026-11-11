// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { ReviewMenu } from './ReviewMenu'

const run = (o = {}) => ({ id: 'r', status: 'running', total: 19, done: 7, ...o }) as never

test('Check citations starts a check', async () => {
  const onCheck = vi.fn()
  render(<ReviewMenu hasWorkspace run={null} onCheck={onCheck} onCancel={() => {}} />)
  fireEvent.keyDown(screen.getByRole('button', { name: /review/i }), { key: 'Enter' })
  await fireEvent.click(await screen.findByRole('menuitem', { name: 'Check citations' }))
  expect(onCheck).toHaveBeenCalled()
})

test('without a workspace it says why and cannot start', async () => {
  const onCheck = vi.fn()
  render(<ReviewMenu hasWorkspace={false} run={null} onCheck={onCheck} onCancel={() => {}} />)
  fireEvent.keyDown(screen.getByRole('button', { name: /review/i }), { key: 'Enter' })
  expect(await screen.findByText('Pick a workspace first')).toBeInTheDocument()
  await fireEvent.click(screen.getByRole('menuitem', { name: 'Check citations' }))
  expect(onCheck).not.toHaveBeenCalled()
})

test('a live run shows progress and Cancel', async () => {
  const onCancel = vi.fn()
  render(<ReviewMenu hasWorkspace run={run()} onCheck={() => {}} onCancel={onCancel} />)
  expect(screen.getByText('Checking 7 of 19…')).toBeInTheDocument()
  await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(onCancel).toHaveBeenCalled()
})

test('Review this section works without a workspace and is off while a section review is live', async () => {
  const onReviewSection = vi.fn()
  const { unmount } = render(<ReviewMenu hasWorkspace={false} run={null} onCheck={() => {}} onCancel={() => {}} onReviewSection={onReviewSection} />)
  fireEvent.keyDown(screen.getByRole('button', { name: /review/i }), { key: 'Enter' })
  await fireEvent.click(await screen.findByRole('menuitem', { name: 'Review this section' }))
  expect(onReviewSection).toHaveBeenCalled()
  unmount()
  render(<ReviewMenu hasWorkspace run={null} onCheck={() => {}} onCancel={() => {}} onReviewSection={onReviewSection} sectionLive />)
  fireEvent.keyDown(screen.getByRole('button', { name: /review/i }), { key: 'Enter' })
  expect(await screen.findByRole('menuitem', { name: 'Review this section' })).toHaveAttribute('aria-disabled', 'true')
})

test('"Pick a workspace first" sits right under Check citations', async () => {
  render(<ReviewMenu hasWorkspace={false} run={null} onCheck={() => {}} onCancel={() => {}} onReviewSection={() => {}} />)
  fireEvent.keyDown(screen.getByRole('button', { name: /review/i }), { key: 'Enter' })
  const check = await screen.findByRole('menuitem', { name: 'Check citations' })
  expect(check.nextElementSibling).toHaveTextContent('Pick a workspace first')
})

test('Review all files calls onCheckAll; it is off without a workspace or while a run is live', async () => {
  const onCheckAll = vi.fn()
  const { unmount } = render(<ReviewMenu hasWorkspace run={null} onCheck={() => {}} onCancel={() => {}} onCheckAll={onCheckAll} />)
  fireEvent.keyDown(screen.getByRole('button', { name: /review/i }), { key: 'Enter' })
  await fireEvent.click(await screen.findByRole('menuitem', { name: 'Review all files' }))
  expect(onCheckAll).toHaveBeenCalled()
  unmount()
  const again = render(<ReviewMenu hasWorkspace={false} run={null} onCheck={() => {}} onCancel={() => {}} onCheckAll={onCheckAll} />)
  fireEvent.keyDown(screen.getByRole('button', { name: /review/i }), { key: 'Enter' })
  expect(await screen.findByRole('menuitem', { name: 'Review all files' })).toHaveAttribute('aria-disabled', 'true')
  again.unmount()
  render(<ReviewMenu hasWorkspace run={run({ file: '*' })} onCheck={() => {}} onCancel={() => {}} onCheckAll={onCheckAll} />)
  fireEvent.keyDown(screen.getByRole('button', { name: /review/i }), { key: 'Enter' })
  expect(await screen.findByRole('menuitem', { name: 'Review all files' })).toHaveAttribute('aria-disabled', 'true')
})

test('Download report is a link only for a finished all-files run that has a report', async () => {
  const href = '/api/manuscripts/m/review/report.md'
  const { unmount } = render(<ReviewMenu hasWorkspace run={run({ status: 'done', file: '*', done: 19, total: 19 })} onCheck={() => {}} onCancel={() => {}} onCheckAll={() => {}} reportHref={href} />)
  fireEvent.keyDown(screen.getByRole('button', { name: /review/i }), { key: 'Enter' })
  const link = await screen.findByRole('menuitem', { name: 'Download report' })
  expect(link.getAttribute('href')).toMatch(/\/review\/report\.md$/)
  unmount()
  for (const r of [run({ status: 'done', file: 'main.tex' }), run({ status: 'running', file: '*' }), null]) {
    const view = render(<ReviewMenu hasWorkspace run={r} onCheck={() => {}} onCancel={() => {}} onCheckAll={() => {}} reportHref={href} />)
    fireEvent.keyDown(screen.getAllByRole('button', { name: /review/i }).at(-1)!, { key: 'Enter' })
    await screen.findByRole('menuitem', { name: 'Review all files' })
    expect(screen.queryByRole('menuitem', { name: 'Download report' })).not.toBeInTheDocument()
    view.unmount()
  }
})
