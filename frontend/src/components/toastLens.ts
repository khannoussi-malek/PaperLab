/**
 * A lens shaped like one Sileo toast, for its liquid glass (see "Notifications" in design-system/MASTER.md).
 *
 * Real glass bends light along its own outline. A toast is a pill sitting on a body, joined by Sileo's gooey curve,
 * so a square map stretched over the toast box would bend the box's edges and miss the pill's. This builds the map
 * from the actual outline instead: a signed distance to the pill and the body, blended smoothly where they meet.
 */

/** Sileo's fixed sizes (0.1.6): the pill's height and the default roundness of both shapes. */
const PILL_HEIGHT = 40
const RADIUS = 16
/** How far the smooth join reaches; about the curve Sileo's goo filter (blur 8 at roundness 16) draws. */
const JOIN = 20
/** How deep into the glass the bending reaches from its edge, in px. */
const BAND = 14
/** How much of that rim stays crisp (unfrosted), in px: thin, so the 40 px pill still has a frosted middle. */
const CRISP = 6

/** A toast's outline, in px from its top-left corner (a top-* position: the body hangs under the pill). */
export type ToastShape = { width: number; height: number; pillX: number; pillWidth: number }

function roundedBox(x: number, y: number, left: number, top: number, right: number, bottom: number) {
  const halfWidth = (right - left) / 2
  const halfHeight = (bottom - top) / 2
  const qx = Math.abs(x - (left + halfWidth)) - (halfWidth - RADIUS)
  const qy = Math.abs(y - (top + halfHeight)) - (halfHeight - RADIUS)
  return Math.hypot(Math.max(qx, 0), Math.max(qy, 0)) + Math.min(Math.max(qx, qy), 0) - RADIUS
}

/** A polynomial smooth minimum: the union of two shapes with a rounded fillet where they meet. */
function smoothUnion(a: number, b: number) {
  const h = Math.max(JOIN - Math.abs(a - b), 0) / JOIN
  return Math.min(a, b) - (h * h * JOIN) / 4
}

/** Signed distance from (x, y) to the toast's outline: negative inside the glass, positive outside. */
export function shapeDistance(shape: ToastShape, x: number, y: number): number {
  const pill = roundedBox(x, y, shape.pillX, 0, shape.pillX + shape.pillWidth, PILL_HEIGHT)
  if (shape.height <= PILL_HEIGHT + 1) return pill
  return smoothUnion(pill, roundedBox(x, y, 0, PILL_HEIGHT, shape.width, shape.height))
}

/**
 * The displacement map, one RGBA pixel per px of the toast. Red is the sideways push and blue the vertical one (128
 * means "don't move"), along the outline's inward normal: the rim draws the page from a little further inside, so what
 * is behind the edge looks stretched round it, like the rim of a thick lens (and never samples past the toast's box,
 * where the backdrop is empty). The push falls off with the square of the depth across `BAND` px and is zero in the
 * middle. Green is how crisp a pixel stays (255 at the edge, 0 from `CRISP` in); the filter frosts the rest.
 */
export function toastLensPixels(shape: ToastShape): Uint8ClampedArray<ArrayBuffer> {
  const { width, height } = shape
  const pixels = new Uint8ClampedArray(width * height * 4)
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4
      const depth = -shapeDistance(shape, x + 0.5, y + 0.5)
      const inBand = depth > 0 && depth < BAND ? 1 - depth / BAND : 0
      const crisp = depth > 0 && depth < CRISP ? 1 - depth / CRISP : 0
      let pushX = 0
      let pushY = 0
      if (inBand > 0) {
        const nx = shapeDistance(shape, x + 1.5, y + 0.5) - shapeDistance(shape, x - 0.5, y + 0.5)
        const ny = shapeDistance(shape, x + 0.5, y + 1.5) - shapeDistance(shape, x + 0.5, y - 0.5)
        const length = Math.hypot(nx, ny) || 1
        const strength = inBand * inBand
        pushX = -(nx / length) * strength
        pushY = -(ny / length) * strength
      }
      pixels[i] = Math.round(128 + 127 * pushX)
      pixels[i + 1] = Math.round(255 * crisp)
      pixels[i + 2] = Math.round(128 + 127 * pushY)
      pixels[i + 3] = 255
    }
  }
  return pixels
}

/** The map as a PNG data URL for `<feImage>`; empty where there is no canvas (tests). */
export function toastLensUrl(shape: ToastShape): string {
  const canvas = document.createElement('canvas')
  canvas.width = shape.width
  canvas.height = shape.height
  const context = canvas.getContext?.('2d')
  if (!context) return ''
  context.putImageData(new ImageData(toastLensPixels(shape), shape.width, shape.height), 0, 0)
  return canvas.toDataURL()
}

type ToastElement = { offsetWidth: number; style: { getPropertyValue: (name: string) => string } }

/** A toast's outline from Sileo's own size variables on it (`--_h`, `--_px`, `--_pw`); null before layout. */
export function readToastShape(toast: ToastElement): ToastShape | null {
  const read = (name: string) => Number.parseFloat(toast.style.getPropertyValue(name))
  const shape = { width: toast.offsetWidth, height: read('--_h'), pillX: read('--_px'), pillWidth: read('--_pw') }
  return shape.width > 0 && Object.values(shape).every(Number.isFinite) ? shape : null
}
