import { useEffect, useMemo } from 'react'
import { Toaster } from 'sileo'
import { bendsLight, LIQUID_CLASS, LIQUID_FILTER_ID, lensMapUrl } from '@/components/liquidGlass'

// Below the shell's h-11 toolbar, so a toast never covers the view's title or actions.
const TOOLBAR_HEIGHT = 44

/** The toast's glass surface filter; index.css applies it to Sileo's blob as `url(#pl-glass-surface)`. */
const SURFACE_FILTER_ID = 'pl-glass-surface'

/** One colour channel bent by `scale`: three of these at slightly different strengths make the colour fringe. */
function Channel({ name, scale, matrix }: { name: string; scale: number; matrix: string }) {
  return (
    <>
      <feDisplacementMap in="SourceGraphic" in2="map" scale={scale} xChannelSelector="R" yChannelSelector="B" result={`${name}-moved`} />
      <feColorMatrix in={`${name}-moved`} type="matrix" values={matrix} result={name} />
    </>
  )
}

/** The `#pl-liquid` filter (see `liquidGlass.ts`). Sizes are fractions of the glass, so one filter fits every toast. */
function GlassFilters() {
  const map = useMemo(() => lensMapUrl(), [])
  return (
    <svg aria-hidden width="0" height="0" className="absolute">
      <filter id={LIQUID_FILTER_ID} primitiveUnits="objectBoundingBox" x="0" y="0" width="1" height="1" colorInterpolationFilters="sRGB">
        {map && <feImage href={map} x="0" y="0" width="1" height="1" preserveAspectRatio="none" result="map" />}
        <Channel name="red" scale={0.1} matrix="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" />
        <Channel name="green" scale={0.09} matrix="0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0" />
        <Channel name="blue" scale={0.08} matrix="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0" />
        <feBlend in="red" in2="green" mode="screen" result="red-green" />
        <feBlend in="red-green" in2="blue" mode="screen" />
      </filter>
    </svg>
  )
}

/**
 * `#pl-glass-surface`, applied to Sileo's blob: what makes it read as a piece of glass rather than a tinted shape.
 * - the body turns 80% opaque, so the frosted, bent page shows through it while text keeps ≥ 5.2:1 on any page;
 * - a bump map from the blob's own outline catches a light from the top left (`feSpecularLighting`): the flat middle
 *   stays clear and only the rounded edge facing the light shines;
 * - a 1 px rim (`--toast-rim`) traces the edge, the bright line real glass has where it turns away from you.
 */
function GlassSurface() {
  return (
    <svg aria-hidden width="0" height="0" className="absolute">
      <filter id={SURFACE_FILTER_ID} x="-5%" y="-5%" width="110%" height="110%" colorInterpolationFilters="sRGB">
        <feComponentTransfer in="SourceGraphic" result="body">
          <feFuncA type="linear" slope="0.8" />
        </feComponentTransfer>
        <feGaussianBlur in="SourceAlpha" stdDeviation="3" result="bump" />
        <feSpecularLighting in="bump" surfaceScale="4" specularConstant="0.9" specularExponent="40" lightingColor="#ffffff" result="light">
          <feDistantLight azimuth="225" elevation="40" />
        </feSpecularLighting>
        <feComposite in="light" in2="SourceAlpha" operator="in" result="shine" />
        <feMorphology in="SourceAlpha" operator="erode" radius="1" result="inside" />
        <feComposite in="SourceAlpha" in2="inside" operator="out" result="edge" />
        <feFlood style={{ floodColor: 'var(--toast-rim)' }} />
        <feComposite in2="edge" operator="in" result="rim" />
        <feMerge>
          <feMergeNode in="body" />
          <feMergeNode in="shine" />
          <feMergeNode in="rim" />
        </feMerge>
      </filter>
    </svg>
  )
}

/**
 * PaperLab's passing notices: Sileo's toasts, drawn as liquid glass (see "Notifications" in design-system/MASTER.md).
 * Mount once at the app root, then call `sileo.success({ title })` and friends from anywhere.
 */
export function Notifications() {
  useEffect(() => {
    if (!bendsLight((navigator as { userAgentData?: Parameters<typeof bendsLight>[0] }).userAgentData, navigator.userAgent)) return
    const root = document.documentElement
    root.classList.add(LIQUID_CLASS)
    return () => root.classList.remove(LIQUID_CLASS)
  }, [])

  return (
    <>
      <GlassFilters />
      <GlassSurface />
      <Toaster position="top-right" offset={{ top: TOOLBAR_HEIGHT }} options={{ duration: 4000 }} />
    </>
  )
}
