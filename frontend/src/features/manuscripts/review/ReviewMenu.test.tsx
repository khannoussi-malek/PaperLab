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
