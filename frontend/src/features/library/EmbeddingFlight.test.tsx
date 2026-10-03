// @vitest-environment jsdom
import { render } from '@testing-library/react'
import { expect, test } from 'vitest'
import { EmbeddingFlight, isEmbedding } from './EmbeddingFlight'

test('isEmbedding is true only while a paper is embedding', () => {
  expect(isEmbedding({ status: 'embedding' })).toBe(true)
  for (const status of ['uploaded', 'extracting', 'chunking', 'enriching', 'ready', 'failed']) {
    expect(isEmbedding({ status })).toBe(false)
  }
})

test('renders a hidden, non-interactive layer of 7 motion-safe pages', () => {
  const { container } = render(<EmbeddingFlight />)
  const layer = container.firstElementChild as HTMLElement
  expect(layer).toHaveAttribute('aria-hidden', 'true')
  const pages = layer.querySelectorAll('.embedding-page')
  expect(pages).toHaveLength(7)
  for (const page of pages) {
    expect(page.className).toContain('motion-safe:animate-')
  }
})

test('the layer never intercepts pointer events', () => {
  const { container } = render(<EmbeddingFlight />)
  const layer = container.firstElementChild as HTMLElement
  expect(layer.className).toContain('pointer-events-none')
})
