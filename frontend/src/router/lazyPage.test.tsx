// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { lazyPage } from './lazyPage'

vi.mock('@/layout/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <div data-testid="shell">{children}</div> }))

const Hello = ({ name }: { name: string }) => <p>hello {name}</p>

test('shows the shell with Loading… until the code arrives, then the page with its props', async () => {
  const Page = lazyPage(() => Promise.resolve(Hello))
  render(<Page name="ada" />)
  expect(screen.getByTestId('shell')).toHaveTextContent('Loading…')
  expect(await screen.findByText('hello ada')).toBeInTheDocument()
})

test('a bare page loads without the shell', async () => {
  const Page = lazyPage(() => Promise.resolve(Hello), { bare: true })
  render(<Page name="ada" />)
  expect(screen.queryByTestId('shell')).toBeNull()
  expect(await screen.findByText('hello ada')).toBeInTheDocument()
})

test('a remount of a loaded page renders at once, without Loading…', async () => {
  const Page = lazyPage(() => Promise.resolve(Hello))
  const { unmount } = render(<Page name="ada" />)
  await screen.findByText('hello ada')
  unmount()
  render(<Page name="bo" />)
  expect(screen.getByText('hello bo')).toBeInTheDocument()
})

test('a chunk that fails shows Try again, which loads it afresh', async () => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
  const load = vi.fn<() => Promise<typeof Hello>>().mockRejectedValueOnce(new Error('chunk failed')).mockResolvedValue(Hello)
  const Page = lazyPage(load)
  render(<Page name="ada" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Try again' }))
  expect(await screen.findByText('hello ada')).toBeInTheDocument()
  expect(load).toHaveBeenCalledTimes(2)
})
