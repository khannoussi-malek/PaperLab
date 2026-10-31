// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { ShortcutHelp } from './ShortcutHelp'

afterEach(cleanup)

// `?` opens the help with no trigger to return to, so closing it hands focus back through returnFocus.
it('calls returnFocus when the help closes', async () => {
  const back = vi.fn()
  function Host() {
    const [open, setOpen] = useState(true)
    return <ShortcutHelp open={open} onOpenChange={setOpen} returnFocus={back} />
  }
  render(<Host />)
  fireEvent.keyDown(await screen.findByRole('dialog'), { key: 'Escape' })
  await waitFor(() => expect(back).toHaveBeenCalledTimes(1))
})
