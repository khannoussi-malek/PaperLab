// The 2D canvases the app's 3D scenes show as textures, in the brand's colours. Ported from the startup scene.
import * as THREE from 'three'

export const C = {
  white: '#ffffff', line: '#e2e8f0', line2: '#cbd5e1', title: '#334155', muted: '#475569', mutedD: '#94a3b8',
  yellow: '#facc15', wire: '#eab308',
}

type Paint = (c: CanvasRenderingContext2D, w: number, h: number) => void

/** A texture painted at 2x, so edges stay crisp up close; `paint` still draws in w × h units. */
export function texture(w: number, h: number, paint: Paint): THREE.CanvasTexture {
  const canvas = Object.assign(document.createElement('canvas'), { width: w * 2, height: h * 2 })
  const c = canvas.getContext('2d')!
  c.scale(2, 2)
  paint(c, w, h)
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  return tex
}

/** A page like the mark: title bar and text lines; `band` bakes in the yellow highlight (the flying pages). */
export function paintPage(c: CanvasRenderingContext2D, w: number, band: boolean) {
  const u = w / 640
  const bar = (x: number, y: number, bw: number, bh: number, col: string) => {
    c.fillStyle = col
    c.beginPath()
    c.roundRect(x * u, y * u, bw * u, bh * u, (bh / 2) * u)
    c.fill()
  }
  c.fillStyle = C.white
  c.strokeStyle = C.line2
  c.lineWidth = 3 * u
  c.beginPath()
  c.roundRect(2 * u, 2 * u, w - 4 * u, 836 * u, 44 * u)
  c.fill()
  c.stroke()
  bar(80, 90, 440, 36, C.title)
  ;[480, 470, 440, 480, 480, 460, 480, 300, 480, 450, 470, 360].forEach((lw, i) => {
    const y = 190 + i * 52
    if (i !== 4) return bar(80, y, lw, 18, C.line)
    if (band) {
      c.globalAlpha = 0.7
      bar(60, y - 24, 520, 66, C.yellow)
      c.globalAlpha = 1
    }
    bar(80, y, 480, 18, C.muted)
  })
}

export const pageTexture = (band: boolean) => texture(320, 420, (c, w) => paintPage(c, w, band))

/** A rounded marker stroke in white, tinted by its material. */
export const strokeTexture = () =>
  texture(260, 33, (c, w, h) => {
    c.fillStyle = '#fff'
    c.beginPath()
    c.roundRect(0, 0, w, h, h / 2)
    c.fill()
  })

/** A wide, flat glow: a circle squashed into an ellipse that fades to nothing (never a round blob). */
export const glowTexture = () =>
  texture(512, 128, (c, w, h) => {
    c.transform(1, 0, 0, h / w, 0, 0) // on top of the 2x scale, never setTransform
    const g = c.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2)
    g.addColorStop(0, 'rgba(250, 204, 21, 0.9)')
    g.addColorStop(0.35, 'rgba(250, 204, 21, 0.35)')
    g.addColorStop(1, 'rgba(250, 204, 21, 0)')
    c.fillStyle = g
    c.fillRect(0, 0, w, w)
  })

/** The sheen's beam: a soft bright stripe down the middle of a wide texture. */
export const beamTexture = () =>
  texture(512, 64, (c, w, h) => {
    const g = c.createLinearGradient(0, 0, w, 0)
    g.addColorStop(0.38, 'rgba(255,255,255,0)')
    g.addColorStop(0.5, 'rgba(255,255,255,1)')
    g.addColorStop(0.62, 'rgba(255,255,255,0)')
    c.fillStyle = g
    c.fillRect(0, 0, w, h)
  })

/** The card's rounded outline in white, for alpha-masking the sheen to the page. */
export const outlineTexture = () =>
  texture(320, 420, (c, w, h) => {
    c.fillStyle = '#fff'
    c.beginPath()
    c.roundRect(2, 2, w - 4, h - 4, 22)
    c.fill()
  })

export const shadowTexture = () =>
  texture(320, 400, (c, w, h) => {
    c.filter = 'blur(22px)'
    c.fillStyle = 'rgba(15, 23, 42, 0.32)'
    c.beginPath()
    c.roundRect(50, 50, w - 100, h - 100, 24)
    c.fill()
  })

export const dotTexture = () =>
  texture(32, 32, (c) => {
    const g = c.createRadialGradient(16, 16, 0, 16, 16, 16)
    g.addColorStop(0, 'rgba(255,255,255,1)')
    g.addColorStop(1, 'rgba(255,255,255,0)')
    c.fillStyle = g
    c.fillRect(0, 0, 32, 32)
  })
