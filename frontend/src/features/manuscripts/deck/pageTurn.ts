export type TurnDir = 'fwd' | 'bwd'
export type TurnOpts = {
  /** Reduced motion: swap instantly, no leaf. */
  still?: boolean
  /** Runs first: sets the page the leaf uncovers. */
  uncover?: () => void
  /** Runs when the leaf has landed (or was finished early): sets the far page. */
  land?: () => void
  /** Extra classes on the front face (e.g. the cover). */
  frontClass?: string
}

export const TURN_MS = 850
const EASE = 'cubic-bezier(.45,.05,.3,1)'

/** The paper look of a page; PaperBook uses it for the resting pages too. */
export const PAGE_CLASS =
  'absolute top-0 box-border h-[260px] w-[160px] overflow-hidden bg-[#fffdf8] p-3.5 font-serif text-[10px] text-neutral-900'

const SHADE: Record<string, string> = {
  'fwd-front': 'bg-[linear-gradient(to_right,rgba(0,0,0,.05),rgba(0,0,0,.35))]',
  'fwd-back': 'bg-[linear-gradient(to_left,rgba(0,0,0,.05),rgba(0,0,0,.35))]',
  'bwd-front': 'bg-[linear-gradient(to_left,rgba(0,0,0,.05),rgba(0,0,0,.35))]',
  'bwd-back': 'bg-[linear-gradient(to_right,rgba(0,0,0,.05),rgba(0,0,0,.35))]',
}

const noop = { finish() {} }
const active = new WeakMap<HTMLElement, { finish(): void }>()

function face(side: 'front' | 'back', dir: TurnDir, content: Node | string, extra = ''): HTMLElement {
  const el = document.createElement('div')
  el.className = `${PAGE_CLASS} inset-0 [backface-visibility:hidden] ${side === 'back' ? '[transform:rotateY(180deg)]' : ''} ${extra}`
  if (typeof content === 'string') el.innerHTML = content
  else el.appendChild(content)
  const sh = document.createElement('div')
  sh.dataset.shade = side
  sh.className = `pointer-events-none absolute inset-0 opacity-0 ${SHADE[`${dir}-${side}`]}`
  el.appendChild(sh)
  return el
}

/**
 * Turn one leaf over the spine of `book`. fwd: front = the old right page, back = the new left page.
 * bwd: front = the old left page, back = the new right page. A turn already running is finished first,
 * so the book never shows two leaves. Returns `finish()`, which lands the leaf now (safe to call twice).
 */
export function turnLeaf(book: HTMLElement, dir: TurnDir, front: Node | string, back: Node | string, opts: TurnOpts = {}): { finish(): void } {
  active.get(book)?.finish()
  const { uncover, land, still, frontClass } = opts
  const leaf = document.createElement('div')
  if (still || typeof leaf.animate !== 'function') {
    uncover?.()
    land?.()
    return noop
  }
  leaf.className = `absolute top-0 z-[6] h-[260px] w-[160px] [transform-style:preserve-3d] ${dir === 'fwd' ? 'left-[160px] origin-left' : 'left-0 origin-right'}`
  leaf.append(face('front', dir, front, frontClass), face('back', dir, back))
  const cast = document.createElement('div')
  cast.className = `pointer-events-none absolute top-0 z-[5] h-[260px] w-[160px] opacity-0 ${
    dir === 'fwd' ? 'left-[160px] bg-[linear-gradient(to_right,rgba(0,0,0,.28),transparent_70%)]' : 'left-0 bg-[linear-gradient(to_left,rgba(0,0,0,.28),transparent_70%)]'
  }`
  book.append(cast, leaf)
  uncover?.()

  // lift, bend on the way up, flatten at the top, bend the other way coming down, land
  const s = dir === 'fwd' ? -1 : 1
  const timing = { duration: TURN_MS, easing: EASE }
  const anim = leaf.animate(
    [
      { transform: 'rotateY(0deg) translateZ(1px)' },
      { transform: `rotateY(${s * 40}deg) translateZ(14px) skewY(${s * -5}deg)`, offset: 0.28 },
      { transform: `rotateY(${s * 90}deg) translateZ(22px)`, offset: 0.5 },
      { transform: `rotateY(${s * 140}deg) translateZ(14px) skewY(${s * 5}deg)`, offset: 0.72 },
      { transform: `rotateY(${s * 180}deg) translateZ(1px)` },
    ],
    { ...timing, fill: 'forwards' },
  )
  const shade = (side: string) => leaf.querySelector<HTMLElement>(`[data-shade="${side}"]`)!
  shade('front').animate([{ opacity: 0 }, { opacity: 0.9, offset: 0.5 }, { opacity: 0.9 }], { ...timing, fill: 'forwards' })
  shade('back').animate([{ opacity: 0.9 }, { opacity: 0.9, offset: 0.5 }, { opacity: 0 }], { ...timing, fill: 'forwards' })
  cast.animate([{ opacity: 0 }, { opacity: 1, offset: 0.35 }, { opacity: 0, offset: 0.6 }, { opacity: 0 }], timing)

  let done = false
  const handle = {
    finish() {
      if (done) return
      done = true
      anim.onfinish = null
      anim.cancel()
      leaf.remove()
      cast.remove()
      if (active.get(book) === handle) active.delete(book)
      land?.()
    },
  }
  active.set(book, handle)
  anim.onfinish = handle.finish
  return handle
}
