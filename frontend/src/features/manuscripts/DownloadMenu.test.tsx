// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { DownloadMenu } from './DownloadMenu'

const open = async (hasPdf: boolean) => {
  render(<DownloadMenu manuscript={{ id: 'm1', title: 'My Paper', has_pdf: hasPdf, compiled_at: '2026-10-03T00:00:00Z' }} />)
  fireEvent.keyDown(screen.getByRole('button', { name: 'Download' }), { key: 'Enter' })
  return screen.findByRole('menuitem', { name: /^PDF/ })
}

test('offers the PDF, the LaTeX source alone, and both, each as its own file', async () => {
  const pdf = await open(true)
  expect(pdf).toHaveAttribute('href', '/api/manuscripts/m1/pdf?v=2026-10-03T00%3A00%3A00Z')
  expect(pdf).toHaveAttribute('download', 'My Paper.pdf')
  const latex = screen.getByRole('menuitem', { name: 'LaTeX source (.zip)' })
  expect(latex).toHaveAttribute('href', '/api/manuscripts/m1/export.zip?pdf=false')
  expect(latex).toHaveAttribute('download')
  const both = screen.getByRole('menuitem', { name: 'Source and PDF (.zip)' })
  expect(both).toHaveAttribute('href', '/api/manuscripts/m1/export.zip')
})

test('with no compiled PDF yet, the PDF item is disabled and says to compile first', async () => {
  const pdf = await open(false)
  expect(pdf).toHaveAttribute('aria-disabled', 'true')
  expect(pdf).not.toHaveAttribute('href')
  expect(pdf).toHaveTextContent('PDF — compile first')
  expect(screen.getByRole('menuitem', { name: 'LaTeX source (.zip)' })).not.toHaveAttribute('aria-disabled')
})
