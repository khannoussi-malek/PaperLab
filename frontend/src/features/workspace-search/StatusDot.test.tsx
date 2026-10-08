// @vitest-environment jsdom
import { render } from '@testing-library/react'
import { expect, test } from 'vitest'
import { StatusDot } from './StatusDot'

test('a recognized status gets a colored dot', () => {
  const { container } = render(<StatusDot status="relevant" />)
  expect(container.querySelector('.bg-primary')).toBeInTheDocument()
})

test('an unrecognized or null status (unreviewed, not assessed) gets a neutral outline dot, never uncolored', () => {
  const { container } = render(<StatusDot status={null} />)
  expect(container.querySelector('.border-muted-foreground\\/50')).toBeInTheDocument()
})

test('the dot is decorative — hidden from assistive tech, since the text label stays the real signal', () => {
  const { container } = render(<StatusDot status="not_relevant" />)
  expect(container.querySelector('[aria-hidden="true"]')).toBeInTheDocument()
})
