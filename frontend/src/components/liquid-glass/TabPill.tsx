import { useMemo, type RefObject } from 'react'
import { Channel } from './LiquidGlass'
import { lensUrl } from './lens'
import { channelScales } from './settings'
import { useGlass } from './useGlass'

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
 * The glass pill on a tab bar's active tab (see `useTabPill`), a capsule like Apple's. It glides to a new tab in
 * 650 ms with a slight springy overshoot (slower than the usual 400 ms ceiling: the owner asked to see the glass
 * move); with reduced motion it jumps. Where light bends it is a clear lens over the labels (index.css, "Workspace
 * tab pill"); elsewhere it sits behind them. Render it first inside the TabsList, so the tabs paint over it.
 */
export function TabPill({ thumbRef }: { thumbRef: RefObject<HTMLSpanElement | null> }) {
  const { bendsLight, settings } = useGlass()
  // A lens over the labels only where light can bend, glass is on, and the Buttons area is on (it covers this pill).
  const lens = bendsLight && settings.enabled && settings.areas.buttons
  return (
    <>
      {lens && <TabThumbLens />}
      <span
        ref={thumbRef}
        aria-hidden="true"
        data-tab-thumb
        data-lens={lens ? '' : undefined}
        className="pointer-events-none absolute top-0 left-0 rounded-full bg-glass-strong shadow-sm ring-1 ring-glass-border inset-shadow-[0_1px_0_var(--glass-rim)] motion-safe:data-ready:transition-[transform,width,height] motion-safe:data-ready:duration-650 motion-safe:data-ready:ease-[cubic-bezier(0.34,1.3,0.64,1)]"
      />
    </>
  )
}
