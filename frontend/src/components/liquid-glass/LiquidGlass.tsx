import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { GlassContext, type GlassContextValue } from './useGlass'
import { bendsLight as canBend, lensKey, lensUrl, type LensShape } from './lens'
import {
  blurPx,
  channelScales,
  DEFAULT_GLASS,
  GLASS_AREAS,
  loadGlass,
  saveGlass,
  type GlassArea,
} from './settings'

/**
 * Where each area's glass is (Settings → Glass). Floating surfaces and buttons are found by shadcn's own markers;
 * the shell and the reader mark theirs with `data-glass-area`. Primary buttons are solid, so they're left out.
 */
const AREA_SELECTORS: Record<GlassArea, string> = {
  floating: [
    ...['dropdown-menu', 'dropdown-menu-sub', 'context-menu', 'context-menu-sub', 'popover', 'select', 'dialog'].map(
      (slot) => `[data-slot="${slot}-content"]`,
    ),
    '.citation-card',
    '.reading-popover',
  ].join(','),
  chrome: '[data-glass-area="chrome"]',
  buttons: '[data-slot="button"][data-variant="outline"],[data-slot="button"][data-variant="secondary"]',
  reader: '[data-glass-area="reader"]',
}

/** The class on <html> that turns the bending on (index.css, "Liquid glass"). */
const LIQUID_CLASS = 'liquid'

type Lens = { key: string; shape: LensShape; map: string }

/** One colour channel bent by `scale`: three of these at different strengths make the colour split. */
function Channel({ name, scale, matrix }: { name: string; scale: number; matrix: string }) {
  return (
    <>
      <feDisplacementMap in="SourceGraphic" in2="map" scale={scale} xChannelSelector="R" yChannelSelector="B" result={`${name}-moved`} />
      <feColorMatrix in={`${name}-moved`} type="matrix" values={matrix} result={name} />
    </>
  )
}

function LensFilter({ lens, scales }: { lens: Lens; scales: ReturnType<typeof channelScales> }) {
  const { width, height } = lens.shape
  return (
    <filter id={`lg-${lens.key}`} x="0" y="0" width={width} height={height} filterUnits="userSpaceOnUse" primitiveUnits="userSpaceOnUse" colorInterpolationFilters="sRGB">
      {lens.map && <feImage href={lens.map} x="0" y="0" width={width} height={height} preserveAspectRatio="none" result="map" />}
      <Channel name="red" scale={scales.red} matrix="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" />
      <Channel name="green" scale={scales.green} matrix="0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0" />
      <Channel name="blue" scale={scales.blue} matrix="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0" />
      <feBlend in="red" in2="green" mode="screen" result="red-green" />
      <feBlend in="red-green" in2="blue" mode="screen" />
    </filter>
  )
}

/** How long a resize must settle before its lens is rebuilt; while dragging, the previous lens stays on. */
const RESIZE_SETTLE_MS = 150

/** A surface's corner radius in px; a percentage radius (a circle, a pill) is a share of its shorter side. */
function radiusOf(element: HTMLElement, width: number, height: number) {
  const raw = getComputedStyle(element).borderTopLeftRadius
  const value = Number.parseFloat(raw) || 0
  return raw.endsWith('%') ? (value / 100) * Math.min(width, height) : value
}

/**
 * Finds every glass surface of the switched-on areas, keeps it marked (`data-lg`) and pointed at a lens of its own
 * size and corner radius (`--lg-lens`), and returns the lenses to draw. A full search runs only when a matching
 * surface is added or removed (a menu opening); sizes come from a ResizeObserver, which also notices a surface that
 * starts hidden and appears later. A new Edge width swaps the lenses in place, so dragging it never flickers.
 */
function useLenses(selector: string, edge: number): Lens[] {
  const [lenses, setLenses] = useState<Lens[]>([])
  const edgeRef = useRef(edge)
  const resyncRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    edgeRef.current = edge
    resyncRef.current?.()
  }, [edge])

  useEffect(() => {
    if (!selector) return
    const watched = new Set<HTMLElement>()
    const shapes = new Map<HTMLElement, LensShape>()
    const dirty = new Set<Element>()
    const maps = new Map<string, string>()
    let frame = 0
    let settle = 0
    let sweep = true
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(sync)
    }
    const resize = new ResizeObserver((entries) => {
      for (const entry of entries) dirty.add(entry.target)
      clearTimeout(settle)
      settle = window.setTimeout(schedule, RESIZE_SETTLE_MS)
    })
    const unmark = (element: HTMLElement) => {
      delete element.dataset.lg
      element.style.removeProperty('--lg-lens')
      shapes.delete(element)
    }
    const unwatch = (element: HTMLElement) => {
      unmark(element)
      resize.unobserve(element)
      watched.delete(element)
    }
    function sync() {
      frame = 0
      const currentEdge = edgeRef.current
      if (sweep) {
        sweep = false
        const found = new Set(document.querySelectorAll<HTMLElement>(selector))
        for (const element of [...watched]) if (!found.has(element)) unwatch(element)
        for (const element of found) {
          if (watched.has(element)) continue
          watched.add(element)
          resize.observe(element)
          dirty.add(element)
        }
      }
      for (const element of dirty) {
        if (!(element instanceof HTMLElement) || !watched.has(element)) continue
        const width = element.offsetWidth
        const height = element.offsetHeight
        if (width < 1 || height < 1) unmark(element)
        else shapes.set(element, { width, height, radius: radiusOf(element, width, height) })
      }
      dirty.clear()
      const next = new Map<string, LensShape>()
      for (const [element, shape] of shapes) {
        const key = lensKey(shape, currentEdge)
        next.set(key, shape)
        const lens = `url(#lg-${key})`
        if (element.style.getPropertyValue('--lg-lens') !== lens) element.style.setProperty('--lg-lens', lens)
        element.dataset.lg = ''
      }
      for (const key of [...maps.keys()]) if (!next.has(key)) maps.delete(key)
      for (const [key, shape] of next) if (!maps.has(key)) maps.set(key, lensUrl(shape, currentEdge))
      setLenses((current) =>
        current.length === next.size && current.every((lens) => next.has(lens.key))
          ? current
          : [...next].map(([key, shape]) => ({ key, shape, map: maps.get(key) ?? '' })),
      )
    }
    const mutations = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === 'attributes') sweep = true
        for (const node of record.addedNodes) {
          if (node instanceof Element && (node.matches(selector) || node.querySelector(selector))) sweep = true
        }
        if (record.removedNodes.length > 0 && [...watched].some((element) => !element.isConnected)) sweep = true
      }
      if (sweep) schedule()
    })
    // data-variant: a button that turns outline (or stops being one) joins or leaves the glass.
    mutations.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-variant'] })
    resyncRef.current = schedule
    schedule()
    return () => {
      resyncRef.current = null
      mutations.disconnect()
      cancelAnimationFrame(frame)
      clearTimeout(settle)
      for (const element of [...watched]) unwatch(element)
      resize.disconnect()
    }
  }, [selector])
  return selector ? lenses : []
}

/**
 * Liquid glass across the app (see "Glass" in design-system/MASTER.md): the settings, applied live, and the lenses
 * that bend the page behind each glass surface. Wrap the app once.
 */
export function LiquidGlassProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState(() => loadGlass(localStorage))
  const [bendsLight] = useState(() =>
    canBend((navigator as { userAgentData?: Parameters<typeof canBend>[0] }).userAgentData, navigator.userAgent),
  )
  const active = settings.enabled && bendsLight
  const selector = active ? GLASS_AREAS.filter((area) => settings.areas[area]).map((area) => AREA_SELECTORS[area]).join(',') : ''
  const lenses = useLenses(selector, settings.edgeWidth)

  // Saved after the change lands, not inside the state updater (StrictMode runs updaters twice).
  const saved = useRef(settings)
  useEffect(() => {
    if (saved.current === settings) return
    saved.current = settings
    saveGlass(settings, localStorage)
  }, [settings])

  useEffect(() => {
    const root = document.documentElement
    root.style.setProperty('--lg-blur', `${blurPx(settings)}px`)
    root.style.setProperty('--lg-saturate', `${settings.saturation}%`)
    root.style.setProperty('--lg-opacity', String(settings.opacity))
    root.classList.toggle(LIQUID_CLASS, active)
    return () => root.classList.remove(LIQUID_CLASS)
  }, [settings, active])

  const context = useMemo<GlassContextValue>(
    () => ({
      settings,
      bendsLight,
      update: (patch) => setSettings((current) => ({ ...current, ...patch })),
      reset: () => setSettings(DEFAULT_GLASS),
    }),
    [settings, bendsLight],
  )
  const scales = channelScales(settings)

  return (
    <GlassContext.Provider value={context}>
      {children}
      <svg aria-hidden width="0" height="0" className="pointer-events-none absolute">
        {lenses.map((lens) => (
          <LensFilter key={lens.key} lens={lens} scales={scales} />
        ))}
      </svg>
    </GlassContext.Provider>
  )
}
