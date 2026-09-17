import { afterEach, describe, expect, it, vi } from 'vitest'
import { copyText } from './clipboard'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('copyText', () => {
  it('writes the text to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })

    await copyText('{"mcpServers": {}}')

    expect(writeText).toHaveBeenCalledWith('{"mcpServers": {}}')
  })

  it('says why when the browser offers no clipboard here', async () => {
    vi.stubGlobal('navigator', {})

    await expect(copyText('x')).rejects.toThrow('Copying needs clipboard access, which this browser blocks here.')
  })

  it('says why when the browser refuses the write', async () => {
    vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockRejectedValue(new DOMException('denied')) } })

    await expect(copyText('x')).rejects.toThrow('Could not copy: the browser blocked clipboard access.')
  })
})
