/**
 * Liquid glass: the light-bending edge of Apple's Liquid Glass (see "Glass" in design-system/MASTER.md).
 *
 * The technique is liquid-glass-react's (rdev/liquid-glass-react): a displacement map pushes the page behind the glass
 * outwards near its edges, three times with slightly different strengths (red, green, blue) for the colour fringe.
 * That library only draws it inside its own floating component, so PaperLab builds the same SVG filter once
 * (`GlassFilters`) and surfaces opt in with `backdrop-filter: url(#pl-liquid)`.
 */

/** The filter's id; CSS refers to it as `url(#pl-liquid)`. */
export const LIQUID_FILTER_ID = 'pl-liquid'

/** The class on <html> that turns the bending on; only set where the browser can do it. */
export const LIQUID_CLASS = 'liquid'

/**
 * A square displacement map, as RGBA pixels. Red is the sideways push (by x), blue the vertical one (by y); 128 means
 * "don't move". The middle stays at 128 and only the outer `edge` fraction curves to 1 or 255, so the centre of a
 * surface shows the page undistorted, like the flat middle of a lens.
 */
export function lensPixels(size: number, edge: number): Uint8ClampedArray<ArrayBuffer> {
  // Squared, so the push is gentle where the band starts and steep at the very edge: the curve of a lens's rim.
  const curve = (depth: number) => depth * depth
  const bend = (t: number) => (t < edge ? -curve((edge - t) / edge) : t > 1 - edge ? curve((t - (1 - edge)) / edge) : 0)
  const pixels = new Uint8ClampedArray(size * size * 4)
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const i = (y * size + x) * 4
      pixels[i] = Math.round(128 + 127 * bend(x / (size - 1)))
      pixels[i + 1] = 128
      pixels[i + 2] = Math.round(128 + 127 * bend(y / (size - 1)))
      pixels[i + 3] = 255
    }
  }
  return pixels
}

/** The map as a PNG data URL for `<feImage>`; empty where there is no canvas (tests), which leaves the filter inert. */
export function lensMapUrl(size = 128, edge = 0.3): string {
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const context = canvas.getContext?.('2d')
  if (!context) return ''
  context.putImageData(new ImageData(lensPixels(size, edge), size, size), 0, 0)
  return canvas.toDataURL()
}

type UserAgentData = { brands: { brand: string; version: string }[] }

/**
 * Whether this browser bends light. Only Chromium (Chrome, Edge, Arc, and the Electron desktop app) runs an SVG filter
 * inside `backdrop-filter`; Safari and Firefox drop the whole declaration, so they keep the frosted glass instead.
 */
export function bendsLight(userAgentData: UserAgentData | undefined, userAgent: string): boolean {
  if (userAgentData) return userAgentData.brands.some(({ brand }) => brand === 'Chromium')
  // Chrome, Edge and Electron all say "Chrome/"; Safari and Firefox never do.
  return /\bChrome\/\d/.test(userAgent)
}
