import { Fragment, useLayoutEffect, useMemo, useRef } from 'react'
import { Channel } from '@/components/liquid-glass/LiquidGlass'
import { lensUrl } from '@/components/liquid-glass/lens'
import { channelScales } from '@/components/liquid-glass/settings'
import { useGlass } from '@/components/liquid-glass/useGlass'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { WorkspaceTab } from '@/lib/route'
import { Term } from './Term'
import { GROUP_LABELS, WORKSPACE_TABS, tabAriaLabel } from './workspaceTabs'

type Counts = Partial<Record<WorkspaceTab, number>>

/** The step line, with "PRISMA" explained wherever it appears. */
function StepLine({ text }: { text: string }) {
  const [before, ...after] = text.split('PRISMA')
  if (!after.length) return <>{text}</>
  return (
    <>
      {before}
      <Term term="prisma">PRISMA</Term>
      {after.join('PRISMA')}
    </>
  )
}

/**
 * Keeps the active tab in view and the glass pill (`thumb`) on it: placed before the first paint, then moved on every tab change
 * and whenever the tab's size changes (a count arriving, a font loading). It writes the pill's style directly, so a
 * move costs no React render; the pill's own CSS transition does the sliding.
 */
function useTabThumb(active: WorkspaceTab) {
  const list = useRef<HTMLDivElement>(null)
  const thumb = useRef<HTMLSpanElement>(null)
  useLayoutEffect(() => {
    const tab = list.current?.querySelector<HTMLElement>('[data-state="active"]')
    const pill = thumb.current
    if (!tab || !pill || !list.current) return
    // On a narrow screen the list scrolls sideways: bring the chosen tab into view.
    tab.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
    const place = () => {
      pill.style.transform = `translate(${tab.offsetLeft}px, ${tab.offsetTop}px)`
      pill.style.width = `${tab.offsetWidth}px`
      pill.style.height = `${tab.offsetHeight}px`
      // From now on moves animate; the first placement above happened before the first paint, so it doesn't.
      pill.dataset.ready = ''
    }
    place()
    // ponytail: every browser has ResizeObserver; only bare test environments lack it, and there one placement does.
    if (typeof ResizeObserver === 'undefined') return
    const resize = new ResizeObserver(place)
    resize.observe(tab)
    resize.observe(list.current)
    return () => resize.disconnect()
  }, [active])
  return { listRef: list, thumbRef: thumb }
}

/** The shape the tab lens's map is drawn for. The filter stretches it over the pill (its units are fractions of the
 * pill), so the lens keeps fitting while the pill changes width mid-slide. */
const THUMB_MAP = { width: 160, height: 32, radius: 16 }
/** The tab lens's rim depth in px of the map, and how Displacement Scale converts to its units (see TabThumbLens). */
const THUMB_EDGE = 6
const THUMB_STRENGTH = 650

/**
 * `#lg-tab-thumb`: the pill as a clear lens (liquid-glass-react's technique, Settings → Glass's strengths). Its edges
 * bend and colour-split the labels it slides over; its middle stays flat, so the active label reads sharp.
 */
function TabThumbLens() {
  const { settings } = useGlass()
  // A thin rim: on a 32 px pill a deeper band would bend the whole label.
  const map = useMemo(() => lensUrl(THUMB_MAP, Math.min(settings.edgeWidth, THUMB_EDGE)), [settings.edgeWidth])
  const scales = channelScales(settings)
  // In these units Chromium scales the push by the pill's width, so Displacement Scale is brought down to a few px at
  // the rim (70 → about 8 px on a typical tab); the slider still turns it up.
  const fraction = (px: number) => px / THUMB_STRENGTH
  return (
    <svg aria-hidden width="0" height="0" className="absolute">
      <filter id="lg-tab-thumb" x="0" y="0" width="1" height="1" primitiveUnits="objectBoundingBox" colorInterpolationFilters="sRGB">
        {map && <feImage href={map} x="0" y="0" width="1" height="1" preserveAspectRatio="none" result="map" />}
        <Channel name="red" scale={fraction(scales.red)} matrix="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" />
        <Channel name="green" scale={fraction(scales.green)} matrix="0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0" />
        <Channel name="blue" scale={fraction(scales.blue)} matrix="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0" />
        <feBlend in="red" in2="green" mode="screen" result="red-green" />
        <feBlend in="red-green" in2="blue" mode="screen" />
      </filter>
    </svg>
  )
}

/**
 * The active tab's own fill and shadow are switched off: the sliding glass pill is its background (see "Workspaces"
 * in design-system/MASTER.md).
 */
const PILL_TAB =
  'data-active:bg-transparent data-active:shadow-none group-data-[variant=default]/tabs-list:data-active:shadow-none dark:data-active:border-transparent dark:data-active:bg-transparent'

/** Two labelled groups of tabs, then one muted line saying what the active tab is for. Must sit inside <Tabs>. */
export function WorkspaceTabBar({ active, counts }: { active: WorkspaceTab; counts: Counts }) {
  const { listRef, thumbRef } = useTabThumb(active)
  const glassSettings = useGlass()
  // A lens over the labels only where light can bend, glass is on, and the Buttons area is on (it covers this pill).
  const lens = glassSettings.bendsLight && glassSettings.settings.enabled && glassSettings.settings.areas.buttons
  const current = WORKSPACE_TABS.find((tab) => tab.value === active)
  return (
    <div className="flex flex-col gap-2">
      <TabsList
        ref={listRef}
        className={cn(
          // Tinted glass with a lit edge, but no blur of its own: a blurring bar would be a backdrop root, and the lens pill
          // inside it would then see only the bar, not the labels and page behind.
          'relative h-auto min-w-0 max-w-full justify-start gap-1 overflow-x-auto bg-glass ring-1 ring-glass-border inset-shadow-[0_1px_0_var(--glass-rim)] max-md:[mask-image:linear-gradient(to_right,transparent,black_1rem,black_calc(100%-1rem),transparent)]',
        )}
      >
        {/* The glass pill on the active tab, a capsule like Apple's. It glides to a new tab in 650 ms with a slight
            springy overshoot (slower than the usual 400 ms ceiling: the owner asked to see the glass move); with
            reduced motion it jumps. Where light bends it is a clear lens over the labels (index.css, "Workspace tab
            pill"); elsewhere it sits behind them, so it comes first and the tabs paint over it. */}
        {lens && <TabThumbLens />}
        <span
          ref={thumbRef}
          aria-hidden="true"
          data-tab-thumb
          data-lens={lens ? '' : undefined}
          className="pointer-events-none absolute top-0 left-0 rounded-full bg-glass-strong shadow-sm ring-1 ring-glass-border inset-shadow-[0_1px_0_var(--glass-rim)] motion-safe:data-ready:transition-[transform,width,height] motion-safe:data-ready:duration-650 motion-safe:data-ready:ease-[cubic-bezier(0.34,1.3,0.64,1)]"
        />
        {(['papers', 'review'] as const).map((group, index) => (
          <Fragment key={group}>
            {index > 0 && <div aria-hidden className="mx-1 w-px shrink-0 self-stretch bg-border" />}
            <span className="sr-only shrink-0 px-1.5 text-xs text-muted-foreground md:not-sr-only">{GROUP_LABELS[group]}</span>
            {WORKSPACE_TABS.filter((tab) => tab.group === group).map((meta) => {
              const count = counts[meta.value]
              return (
                <TabsTrigger key={meta.value} value={meta.value} aria-label={tabAriaLabel(meta, count)} className={cn('min-h-11 shrink-0 md:min-h-0', PILL_TAB)}>
                  {meta.step ? `${meta.step} · ${meta.label}` : meta.label}
                  {count ? <Badge variant="secondary" aria-hidden>{count.toLocaleString('en')}</Badge> : null}
                </TabsTrigger>
              )
            })}
          </Fragment>
        ))}
      </TabsList>
      {current && (
        <p className="text-sm text-muted-foreground max-w-prose">
          <StepLine text={current.stepLine} />
        </p>
      )}
    </div>
  )
}
