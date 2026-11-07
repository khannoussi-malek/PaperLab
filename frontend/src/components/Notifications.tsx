import { useEffect, useRef, useState } from 'react'
import { Toaster } from 'sileo'
import { bendsLight, LIQUID_CLASS } from '@/components/liquidGlass'
import { readToastShape, toastLensUrl, type ToastShape } from '@/components/toastLens'

// Below the shell's h-11 toolbar, so a toast never covers the view's title or actions.
const TOOLBAR_HEIGHT = 44

/** The toast's glass surface filter; index.css applies it to Sileo's blob as `url(#pl-glass-surface)`. */
const SURFACE_FILTER_ID = 'pl-glass-surface'

/** How far the rim bends the page for each colour, in px at the very edge: different, for the colour split. */
const BEND = { red: 52, green: 42, blue: 32 }

type Lens = { id: string; shape: ToastShape; map: string }

/** One colour channel bent by `scale`: three of these at slightly different strengths make the colour split. */
function Channel({ name, scale, matrix }: { name: string; scale: number; matrix: string }) {
  return (
    <>
      <feDisplacementMap in="SourceGraphic" in2="map" scale={scale} xChannelSelector="R" yChannelSelector="B" result={`${name}-moved`} />
      <feColorMatrix in={`${name}-moved`} type="matrix" values={matrix} result={name} />
    </>
  )
}

/**
 * One toast's lens (liquid-glass-react's technique, on a map shaped like this toast; see `toastLens.ts`): the page
 * behind is bent along the outline, red, green and blue by different amounts, so colours split and curve round the
 * rim like real glass. A thin rim stays crisp; the middle, behind the text, is frosted.
 */
function LensFilter({ lens }: { lens: Lens }) {
  const { width, height } = lens.shape
  return (
    <filter id={lens.id} x="0" y="0" width={width} height={height} filterUnits="userSpaceOnUse" primitiveUnits="userSpaceOnUse" colorInterpolationFilters="sRGB">
      {lens.map && <feImage href={lens.map} x="0" y="0" width={width} height={height} preserveAspectRatio="none" result="map" />}
      <Channel name="red" scale={BEND.red} matrix="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" />
      <Channel name="green" scale={BEND.green} matrix="0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0" />
      <Channel name="blue" scale={BEND.blue} matrix="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0" />
      <feBlend in="red" in2="green" mode="screen" result="red-green" />
      <feBlend in="red-green" in2="blue" mode="screen" result="bent" />
      <feGaussianBlur in="bent" stdDeviation="7" result="frost" />
      <feColorMatrix in="map" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 1 0 0 0" result="edge" />
      <feComposite in="bent" in2="edge" operator="in" result="rim" />
      <feMerge>
        <feMergeNode in="frost" />
        <feMergeNode in="rim" />
      </feMerge>
    </filter>
  )
}

let lensCount = 0

/**
 * Keeps one lens per toast in `container`, rebuilt whenever Sileo resizes it (its `--_h`, `--_px`, `--_pw`), and points
 * the toast at it through `--pl-lens`. Only where the browser bends light: elsewhere the toast keeps plain frost.
 */
function useToastLenses(container: React.RefObject<HTMLElement | null>, enabled: boolean): Lens[] {
  const [lenses, setLenses] = useState<Lens[]>([])
  useEffect(() => {
    const root = container.current
    if (!enabled || !root) return
    const ids = new WeakMap<HTMLElement, string>()
    let frame = 0
    const sync = () => {
      frame = 0
      const found = [...root.querySelectorAll<HTMLElement>('[data-sileo-toast]')].flatMap((toast) => {
        const shape = readToastShape(toast)
        if (!shape) return []
        const id = ids.get(toast) ?? `pl-lens-${++lensCount}`
        ids.set(toast, id)
        toast.style.setProperty('--pl-lens', `url(#${id})`)
        return [{ id, shape }]
      })
      setLenses((current) =>
        found.map(({ id, shape }) => {
          const known = current.find((lens) => lens.id === id)
          return known && JSON.stringify(known.shape) === JSON.stringify(shape) ? known : { id, shape, map: toastLensUrl(shape) }
        }),
      )
    }
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(sync)
    }
    const observer = new MutationObserver(schedule)
    observer.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['style'] })
    schedule()
    return () => {
      observer.disconnect()
      cancelAnimationFrame(frame)
    }
  }, [container, enabled])
  return lenses
}

/**
 * `#pl-glass-surface`, applied to Sileo's blob: the glass itself, as thin as glass, so the page shows through.
 * - a faint 12% tint; legibility comes from the backdrop's brightness (`--toast-tone`), as in Apple's glass;
 * - a narrow specular highlight where the rounded edge faces a light from the top left (`feSpecularLighting`);
 * - a soft shade inside the opposite edge (`--toast-shade`) and a hairline rim (`--toast-rim`) for its thickness.
 */
function GlassSurface() {
  return (
    <filter id={SURFACE_FILTER_ID} x="-5%" y="-5%" width="110%" height="110%" colorInterpolationFilters="sRGB">
      <feComponentTransfer in="SourceGraphic" result="body">
        <feFuncA type="linear" slope="0.12" />
      </feComponentTransfer>
      <feGaussianBlur in="SourceAlpha" stdDeviation="3" result="bevel" />
      <feSpecularLighting in="bevel" surfaceScale="5" specularConstant="1" specularExponent="48" lightingColor="#ffffff" result="light">
        <feDistantLight azimuth="225" elevation="30" />
      </feSpecularLighting>
      <feComposite in="light" in2="SourceAlpha" operator="in" result="shine" />
      <feOffset in="bevel" dx="-3" dy="-4" result="lifted" />
      <feComposite in="SourceAlpha" in2="lifted" operator="out" result="far-edge" />
      <feFlood style={{ floodColor: 'var(--toast-shade)' }} />
      <feComposite in2="far-edge" operator="in" result="shade" />
      <feMorphology in="SourceAlpha" operator="erode" radius="1" result="inside" />
      <feComposite in="SourceAlpha" in2="inside" operator="out" result="edge" />
      <feFlood style={{ floodColor: 'var(--toast-rim)' }} />
      <feComposite in2="edge" operator="in" result="rim" />
      <feMerge>
        <feMergeNode in="body" />
        <feMergeNode in="shade" />
        <feMergeNode in="shine" />
        <feMergeNode in="rim" />
      </feMerge>
    </filter>
  )
}

/**
 * PaperLab's passing notices: Sileo's toasts, drawn as liquid glass (see "Notifications" in design-system/MASTER.md).
 * Mount once at the app root, then call `sileo.success({ title })` and friends from anywhere.
 */
export function Notifications() {
  const container = useRef<HTMLDivElement>(null)
  const [liquid] = useState(() =>
    bendsLight((navigator as { userAgentData?: Parameters<typeof bendsLight>[0] }).userAgentData, navigator.userAgent),
  )
  const lenses = useToastLenses(container, liquid)

  useEffect(() => {
    if (!liquid) return
    const root = document.documentElement
    root.classList.add(LIQUID_CLASS)
    return () => root.classList.remove(LIQUID_CLASS)
  }, [liquid])

  return (
    <div ref={container} className="contents">
      <svg aria-hidden width="0" height="0" className="absolute">
        <GlassSurface />
        {lenses.map((lens) => (
          <LensFilter key={lens.id} lens={lens} />
        ))}
      </svg>
      <Toaster position="top-right" offset={{ top: TOOLBAR_HEIGHT }} options={{ duration: 4000 }} />
    </div>
  )
}
