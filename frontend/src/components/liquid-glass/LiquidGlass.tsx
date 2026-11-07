import { useEffect, useMemo, useState, type ReactNode } from 'react'
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

/**
 * Finds every glass surface of the switched-on areas, keeps it marked (`data-lg`) and pointed at a lens of its own
 * size and corner radius (`--lg-lens`), and returns the lenses to draw. New surfaces (a menu opening) are found by a
 * MutationObserver, resized ones by a ResizeObserver; only those are measured again.
 */
function useLenses(selector: string, edge: number): Lens[] {
  const [lenses, setLenses] = useState<Lens[]>([])
  useEffect(() => {
    if (!selector) return
    const shapes = new Map<HTMLElement, LensShape>()
    const dirty = new Set<Element>()
    let frame = 0
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(sync)
    }
    const resize = new ResizeObserver((entries) => {
      for (const entry of entries) dirty.add(entry.target)
      schedule()
    })
    const unmark = (element: HTMLElement) => {
      delete element.dataset.lg
      element.style.removeProperty('--lg-lens')
      resize.unobserve(element)
      shapes.delete(element)
    }
    function sync() {
      frame = 0
      const found = new Set(document.querySelectorAll<HTMLElement>(selector))
      for (const element of [...shapes.keys()]) if (!found.has(element)) unmark(element)
      for (const element of found) {
        if (shapes.has(element) && !dirty.has(element)) continue
        const shape = {
          width: element.offsetWidth,
          height: element.offsetHeight,
          radius: Number.parseFloat(getComputedStyle(element).borderTopLeftRadius) || 0,
        }
        if (shape.width < 1 || shape.height < 1) {
          if (shapes.has(element)) unmark(element)
          continue
        }
        if (!shapes.has(element)) resize.observe(element)
        shapes.set(element, shape)
        element.dataset.lg = ''
        element.style.setProperty('--lg-lens', `url(#lg-${lensKey(shape, edge)})`)
      }
      dirty.clear()
      const byKey = new Map([...shapes.values()].map((shape) => [lensKey(shape, edge), shape]))
      setLenses((current) =>
        [...byKey].map(([key, shape]) => current.find((lens) => lens.key === key) ?? { key, shape, map: lensUrl(shape, edge) }),
      )
    }
    const mutations = new MutationObserver(schedule)
    mutations.observe(document.body, { childList: true, subtree: true })
    schedule()
    return () => {
      mutations.disconnect()
      cancelAnimationFrame(frame)
      for (const element of [...shapes.keys()]) unmark(element)
      resize.disconnect()
    }
  }, [selector, edge])
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
      update: (patch) =>
        setSettings((current) => {
          const next = { ...current, ...patch }
          saveGlass(next, localStorage)
          return next
        }),
      reset: () => {
        saveGlass(DEFAULT_GLASS, localStorage)
        setSettings(DEFAULT_GLASS)
      },
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
