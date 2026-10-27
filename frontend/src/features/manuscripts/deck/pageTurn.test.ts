// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest'
import { turnLeaf } from './pageTurn'

function stubAnimate() {
  const anims: { onfinish: (() => void) | null; cancel: ReturnType<typeof vi.fn> }[] = []
  Element.prototype.animate = vi.fn(function () {
    const a = { onfinish: null, cancel: vi.fn() }
    anims.push(a)
    return a
  }) as never
  return anims
}

describe('turnLeaf', () => {
  it('swaps instantly without Element.animate', () => {
    // @ts-expect-error jsdom
    delete Element.prototype.animate
    const book = document.createElement('div'), calls: string[] = []
    turnLeaf(book, 'fwd', 'a', 'b', { uncover: () => calls.push('u'), land: () => calls.push('l') })
    expect(calls).toEqual(['u', 'l'])
    expect(book.children.length).toBe(0)
  })

  it('swaps instantly when still', () => {
    stubAnimate()
    const book = document.createElement('div'), land = vi.fn()
    turnLeaf(book, 'bwd', 'a', 'b', { still: true, land })
    expect(land).toHaveBeenCalled()
    expect(book.children.length).toBe(0)
  })

  it('runs one leaf, lands on finish, and finishes the previous turn first', () => {
    const anims = stubAnimate()
    const book = document.createElement('div'), l1 = vi.fn(), l2 = vi.fn(), u1 = vi.fn()
    const t1 = turnLeaf(book, 'fwd', '<i>x</i>', 'y', { uncover: u1, land: l1 })
    expect(u1).toHaveBeenCalled()
    expect(book.children.length).toBe(2) // cast + leaf
    expect(l1).not.toHaveBeenCalled()
    turnLeaf(book, 'bwd', 'a', 'b', { land: l2 })
    expect(l1).toHaveBeenCalledTimes(1)
    expect(book.querySelectorAll('[data-shade="front"]').length).toBe(1)
    t1.finish()
    expect(l1).toHaveBeenCalledTimes(1)
    anims[anims.length - 4].onfinish?.() // the second leaf's own animation
    expect(l2).toHaveBeenCalledTimes(1)
    expect(book.children.length).toBe(0)
  })
})
