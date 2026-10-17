// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { UploadPdfsButton } from '@/features/library/UploadPdfsButton'
import { FindPapersButton } from './FindPapersButton'

vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
const wrap = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>)

test('the plain "Find papers" button (library page) opens its dialog', () => {
  wrap(<FindPapersButton />)
  fireEvent.click(screen.getByRole('button', { name: 'Find papers' }))
  expect(screen.getByRole('dialog', { name: 'Find papers' })).toBeTruthy()
})

test('with a label and a tooltip it still opens its dialog', () => {
  wrap(<FindPapersButton label="Find by DOI or title" hint="Look it up." />)
  fireEvent.click(screen.getByRole('button', { name: 'Find by DOI or title' }))
  expect(screen.getByRole('dialog', { name: 'Find papers' })).toBeTruthy()
})

test('"Upload PDFs" still opens the file picker, with or without a tooltip', () => {
  for (const hint of [undefined, 'Add PDFs from your computer.']) {
    const click = vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(() => {})
    const { unmount } = render(<UploadPdfsButton isPending={false} onUpload={vi.fn()} hint={hint} />)
    fireEvent.click(screen.getByRole('button', { name: 'Upload PDFs' }))
    expect(click).toHaveBeenCalledTimes(1)
    click.mockRestore()
    unmount()
  }
})
