/**
 * The lens behind each glass surface ("Glass" in design-system/MASTER.md).
 *
 * The technique is liquid-glass-react's: a displacement map bends the page behind the glass, three times with
 * different strengths (red, green, blue) for a colour split. Its maps are fixed images; PaperLab builds each one from
 * the surface's real size and corner radius, because a map stretched to another shape bends the wrong places.
 */

/** A glass surface's outline, in px. */
export type LensShape = { width: number; height: number; radius: number }

/** Signed distance to a rounded rectangle's outline: negative inside, positive outside. */
function roundedRect({ width, height, radius }: LensShape, x: number, y: number) {
  const r = Math.min(radius, width / 2, height / 2)
  const qx = Math.abs(x - width / 2) - (width / 2 - r)
  const qy = Math.abs(y - height / 2) - (height / 2 - r)
  return Math.hypot(Math.max(qx, 0), Math.max(qy, 0)) + Math.min(Math.max(qx, qy), 0) - r
}

/**
 * The displacement map, one RGBA pixel per px. Red is the sideways push, blue the vertical one, 128 is "don't move".
 * Within `edge` px of the outline the page is drawn from further in, along the inward normal, so what lies behind the
 * rim looks stretched round it like the rim of a thick lens. The push falls off with the square of the depth, and the
 * map never asks for anything outside the surface, where the backdrop is empty.
 */
export function lensPixels(shape: LensShape, edge: number): Uint8ClampedArray<ArrayBuffer> {
  const { width, height } = shape
  const pixels = new Uint8ClampedArray(width * height * 4)
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4
      const depth = -roundedRect(shape, x + 0.5, y + 0.5)
      let pushX = 0
      let pushY = 0
      if (depth > 0 && depth < edge) {
        const nx = roundedRect(shape, x + 1.5, y + 0.5) - roundedRect(shape, x - 0.5, y + 0.5)
        const ny = roundedRect(shape, x + 0.5, y + 1.5) - roundedRect(shape, x + 0.5, y - 0.5)
        const length = Math.hypot(nx, ny) || 1
        const strength = (1 - depth / edge) ** 2
        pushX = -(nx / length) * strength
        pushY = -(ny / length) * strength
      }
      pixels[i] = Math.round(128 + 127 * pushX)
      pixels[i + 1] = 128
      pixels[i + 2] = Math.round(128 + 127 * pushY)
      pixels[i + 3] = 255
    }
  }
  return pixels
}

/** One lens per rounded size: surfaces of the same size (a column of icon buttons) share a filter. */
export const lensKey = ({ width, height, radius }: LensShape, edge: number) =>
  `${Math.round(width)}x${Math.round(height)}r${Math.round(radius)}e${Math.round(edge)}`

/** The map as a PNG data URL for `<feImage>`; empty where there is no canvas (tests), which leaves the lens inert. */
export function lensUrl(shape: LensShape, edge: number): string {
  const width = Math.round(shape.width)
  const height = Math.round(shape.height)
  if (width < 1 || height < 1) return ''
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext?.('2d')
  if (!context) return ''
  context.putImageData(new ImageData(lensPixels({ ...shape, width, height }, edge), width, height), 0, 0)
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
