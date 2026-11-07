import { useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { TabPill } from '@/components/liquid-glass/TabPill'
import { PILL_LIST, PILL_TAB, useTabPill } from '@/components/liquid-glass/useTabPill'
import { Button } from '@/components/ui/button'
import { MenuGlide } from '@/components/ui/menu-glide'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

const STEP = 12
const START = { x: 24, y: 24 }
const MENU_ITEMS = ['Open', 'Rename', 'Add to workspace', 'Delete']

/** Interactive pieces start a click, not a drag of the card. */
const isControl = (target: EventTarget) => target instanceof Element && target.closest('button, [role="tab"]') !== null

/**
 * Settings → Glass's live preview: real glass over a busy, colourful stage (`.glass-stage` in index.css), where the
 * bending shows. A glass card to drag (or move with the arrow keys), the workspace tab bar with its gliding pill, a menu
 * with its gliding highlight, and the three button styles. Every slider applies here at once; the card is lensed
 * whatever the areas say (`data-glass-demo`).
 */
export function GlassPreview() {
  const [position, setPosition] = useState(START)
  const [tab, setTab] = useState('papers')
  const [highlighted, setHighlighted] = useState<string | null>(null)
  const { listRef, thumbRef } = useTabPill(tab)
  const stage = useRef<HTMLDivElement>(null)
  const card = useRef<HTMLDivElement>(null)
  const drag = useRef<{ dx: number; dy: number } | null>(null)

  // Keep the card on the stage; before layout (or in a test) there is nothing to measure, so no clamp.
  const move = (x: number, y: number) => {
    const box = stage.current
    const self = card.current
    if (!box?.clientWidth || !self) return setPosition({ x, y })
    setPosition({
      x: Math.min(Math.max(0, x), box.clientWidth - self.offsetWidth),
      y: Math.min(Math.max(0, y), box.clientHeight - self.offsetHeight),
    })
  }

  const onKeyDown = (event: KeyboardEvent) => {
    const step = event.shiftKey ? STEP * 4 : STEP
    const delta = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[event.key]
    if (!delta) return
    event.preventDefault()
    move(position.x + delta[0], position.y + delta[1])
  }
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (isControl(event.target)) return
    event.currentTarget.setPointerCapture?.(event.pointerId)
    drag.current = { dx: event.clientX - position.x, dy: event.clientY - position.y }
  }
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (drag.current) move(event.clientX - drag.current.dx, event.clientY - drag.current.dy)
  }
  const endDrag = () => {
    drag.current = null
  }

  return (
    <section aria-label="Glass preview" className="flex flex-col gap-2">
      <div ref={stage} className="glass-stage relative h-[30rem] overflow-hidden rounded-xl ring-1 ring-glass-border">
        {/* The stage's words and shapes are there to be bent; they say nothing. */}
        <div aria-hidden className="pointer-events-none absolute inset-0 select-none">
          <p className="absolute top-40 left-6 font-heading text-3xl font-semibold text-slate-900/80 dark:text-white/85">Attention Is All You Need</p>
          <p className="absolute top-52 left-6 max-w-xs font-serif text-lg leading-snug text-slate-800/80 dark:text-white/75">
            The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.
          </p>
          <p className="absolute right-6 bottom-5 font-heading text-4xl font-bold text-pink-600/80 dark:text-pink-300/80">PaperLab</p>
        </div>

        <Tabs value={tab} onValueChange={setTab} className="absolute top-[19.5rem] left-6">
          <TabsList ref={listRef} className={cn(PILL_LIST, 'gap-1')} aria-label="Preview tabs">
            <TabPill thumbRef={thumbRef} />
            {['Papers', 'Notes', 'Chat', 'Evidence'].map((label) => (
              <TabsTrigger key={label} value={label.toLowerCase()} className={PILL_TAB}>
                {label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        {/* A menu surface to look at, not a working menu: hidden from screen readers. */}
        <div
          aria-hidden
          data-glass-demo
          className="absolute top-6 right-6 w-48 rounded-lg bg-glass-strong p-1 text-sm shadow-lg ring-1 ring-glass-border inset-shadow-[0_1px_0_var(--glass-rim)]"
          onPointerLeave={() => setHighlighted(null)}
        >
          <div className="relative">
            <MenuGlide />
            {MENU_ITEMS.map((item) => (
              <div
                key={item}
                data-highlighted={highlighted === item ? '' : undefined}
                onPointerEnter={() => setHighlighted(item)}
                className={cn('relative cursor-default rounded-md px-2 py-1.5', item === 'Delete' && 'text-destructive')}
              >
                {item}
              </div>
            ))}
          </div>
        </div>

        <div className="absolute bottom-20 left-6 flex gap-2">
          <Button type="button">Primary</Button>
          <Button type="button" variant="outline">Outline</Button>
          <Button type="button" variant="secondary">Secondary</Button>
        </div>

        <div
          ref={card}
          role="group"
          aria-label="Glass sample: drag it, or move it with the arrow keys"
          tabIndex={0}
          data-glass-demo
          onKeyDown={onKeyDown}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          style={{ transform: `translate(${position.x}px, ${position.y}px)` }}
          className="absolute top-0 left-0 flex h-28 w-56 cursor-grab touch-none flex-col justify-end rounded-3xl bg-glass p-4 shadow-xl ring-1 ring-glass-border inset-shadow-[0_1px_0_var(--glass-rim)] outline-none select-none focus-visible:ring-3 focus-visible:ring-ring/50 active:cursor-grabbing"
        >
          <span className="text-sm font-medium">Liquid glass</span>
          <span className="text-xs text-muted-foreground">Drag me over the colours</span>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        Drag the glass card over the colours and words, click the tabs, hover the menu. Every slider changes it live.
      </p>
    </section>
  )
}
