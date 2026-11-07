// @vitest-environment jsdom
import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem } from './dropdown-menu'
import { MenuGlide } from './menu-glide'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './select'

// jsdom lays nothing out: stack items 30 px apart, each 28 px tall and 200 px wide.
const itemIndex = (element: HTMLElement) =>
  [...(element.parentElement?.querySelectorAll('[role^="menuitem"], [role="option"]') ?? [])].indexOf(element)
beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'offsetTop', 'get').mockImplementation(function (this: HTMLElement) {
    return 4 + Math.max(0, itemIndex(this)) * 30
  })
  vi.spyOn(HTMLElement.prototype, 'offsetLeft', 'get').mockReturnValue(4)
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(200)
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(28)
  globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }
  Element.prototype.scrollIntoView ??= () => {}
  Element.prototype.hasPointerCapture ??= () => false
})
afterEach(() => vi.restoreAllMocks())

const pill = (root: ParentNode = document) => root.querySelector<HTMLElement>('[data-menu-glide]')!

describe('MenuGlide', () => {
  it('sits on the highlighted item, glides to the next one, and fades out when none is', async () => {
    render(
      <div className="relative">
        <MenuGlide />
        <div role="menuitem">Open</div>
        <div role="menuitem">Rename</div>
        <div role="menuitem">Delete</div>
      </div>,
    )
    const [, rename, remove] = screen.getAllByRole('menuitem')
    expect(pill()).toHaveAttribute('data-hidden')

    await act(async () => rename.setAttribute('data-highlighted', ''))
    expect(pill()).not.toHaveAttribute('data-hidden')
    expect(pill().style.transform).toBe('translate(4px, 34px)')
    expect(pill().style.width).toBe('200px')
    expect(pill().style.height).toBe('28px')

    await act(async () => {
      rename.removeAttribute('data-highlighted')
      remove.setAttribute('data-highlighted', '')
    })
    expect(pill().style.transform).toBe('translate(4px, 64px)')

    await act(async () => remove.removeAttribute('data-highlighted'))
    expect(pill()).toHaveAttribute('data-hidden')
  })

  it('is decoration only: hidden from screen readers, and glides quickly (220 ms), only when motion is allowed', () => {
    render(<div className="relative"><MenuGlide /></div>)
    expect(pill()).toHaveAttribute('aria-hidden', 'true')
    expect(pill().className).toContain('motion-safe:data-ready:duration-220')
  })
})

describe('menus and selects use it', () => {
  it('a dropdown menu has the gliding highlight, and its items paint no highlight of their own', () => {
    render(
      <DropdownMenu open>
        <DropdownMenuContent>
          <DropdownMenuItem>Open</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>,
    )
    expect(pill()).not.toBeNull()
    expect(screen.getByRole('menuitem', { name: 'Open' }).className).not.toContain('focus:bg-accent')
  })

  it('a select has it too, inside its scrolling list', () => {
    render(
      <Select open value="a">
        <SelectTrigger aria-label="Filter">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="a">All papers</SelectItem>
          <SelectItem value="b">Unread</SelectItem>
        </SelectContent>
      </Select>,
    )
    const listbox = screen.getByRole('listbox')
    expect(pill(listbox)).not.toBeNull()
    expect(screen.getByRole('option', { name: 'Unread' }).className).not.toContain('focus:bg-accent')
  })
})
