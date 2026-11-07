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
        <Channel name="red" scale={0.14} matrix="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" />
        <Channel name="green" scale={0.12} matrix="0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0" />
        <Channel name="blue" scale={0.1} matrix="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0" />
        <feBlend in="red" in2="green" mode="screen" result="red-green" />
        <feBlend in="red-green" in2="blue" mode="screen" />
      </filter>
    </svg>
  )
}

/**
 * `#pl-glass-surface`, applied to Sileo's blob: what makes it read as a piece of glass rather than a tinted shape.
 * - the body is clear, a 25% tint, so the frosted, bent page shows through (legibility comes from the backdrop's
 *   brightness, `--toast-backdrop`, as in Apple's glass, not from paint);
 * - the blob's outline, blurred, is a bevel: a key light from the top left and a weaker bounce from the bottom right
 *   (`feSpecularLighting`) make its rounded edge shine while the flat middle stays clear;
 * - a soft inner glow and a hairline rim (`--toast-rim`) give the edge its thickness.
 */
function GlassSurface() {
  return (
    <svg aria-hidden width="0" height="0" className="absolute">
      <filter id={SURFACE_FILTER_ID} x="-5%" y="-5%" width="110%" height="110%" colorInterpolationFilters="sRGB">
        <feComponentTransfer in="SourceGraphic" result="body">
          <feFuncA type="linear" slope="0.25" />
        </feComponentTransfer>
        <feGaussianBlur in="SourceAlpha" stdDeviation="4" result="bevel" />
        <feSpecularLighting in="bevel" surfaceScale="6" specularConstant="1.2" specularExponent="28" lightingColor="#ffffff" result="key">
          <feDistantLight azimuth="225" elevation="32" />
        </feSpecularLighting>
        <feSpecularLighting in="bevel" surfaceScale="6" specularConstant="0.5" specularExponent="28" lightingColor="#ffffff" result="bounce">
          <feDistantLight azimuth="45" elevation="32" />
        </feSpecularLighting>
        <feComposite in="key" in2="bounce" operator="arithmetic" k2="1" k3="1" result="lights" />
        <feComposite in="lights" in2="SourceAlpha" operator="in" result="shine" />
        <feMorphology in="SourceAlpha" operator="erode" radius="3" result="core" />
        <feGaussianBlur in="core" stdDeviation="3" result="soft-core" />
        <feComposite in="SourceAlpha" in2="soft-core" operator="out" result="thickness" />
        <feColorMatrix in="thickness" type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.22 0" result="glow" />
        <feMorphology in="SourceAlpha" operator="erode" radius="1" result="inside" />
        <feComposite in="SourceAlpha" in2="inside" operator="out" result="edge" />
        <feFlood style={{ floodColor: 'var(--toast-rim)' }} />
        <feComposite in2="edge" operator="in" result="rim" />
        <feMerge>
          <feMergeNode in="body" />
          <feMergeNode in="glow" />
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
