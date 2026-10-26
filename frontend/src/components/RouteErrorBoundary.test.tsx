// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { expect, test, vi } from 'vitest'
import { RouteErrorBoundary } from './RouteErrorBoundary'

function Page({ broken }: { broken: boolean }) {
  if (broken) throw new Error('chunk failed')
  return <p>the page</p>
}

test('shows a short message and Try again once the cause is gone', () => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
  let broken = true
  function Host() {
    const [attempt, setAttempt] = useState(0)
    return (
      <RouteErrorBoundary key={attempt} onRetry={() => { broken = false; setAttempt((a) => a + 1) }}>
        <Page broken={broken} />
      </RouteErrorBoundary>
    )
  }
  render(<Host />)
  expect(screen.getByRole('alert')).toHaveTextContent("couldn't load")
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  expect(screen.getByText('the page')).toBeInTheDocument()
})
