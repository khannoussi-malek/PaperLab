import * as THREE from 'three'
import { FADED } from './graphModel'

// The 3D view's papers drawn like the website's scroll scene: a small white page with a title bar, text lines and one
// highlighted line in the paper's workspace colour. Loaded with react-force-graph-3d (Graph3DView), never before.

const PAGE = { w: 128, h: 168 } // texture px; the paper's colour is its highlight
const textures = new Map<string, THREE.CanvasTexture>()

// One texture per colour (a library has a handful of workspace colours), kept for the page's life.
function pageTexture(color: string): THREE.CanvasTexture {
  const cached = textures.get(color)
  if (cached) return cached
  const canvas = Object.assign(document.createElement('canvas'), { width: PAGE.w * 2, height: PAGE.h * 2 })
  const c = canvas.getContext('2d')!
  c.scale(2, 2)
  const bar = (x: number, y: number, w: number, h: number, fill: string) => {
    c.fillStyle = fill
    c.beginPath()
    c.roundRect(x, y, w, h, h / 2)
    c.fill()
  }
  c.fillStyle = '#ffffff'
  c.strokeStyle = '#cbd5e1'
  c.lineWidth = 2
  c.beginPath()
  c.roundRect(1, 1, PAGE.w - 2, PAGE.h - 2, 12)
  c.fill()
  c.stroke()
  bar(16, 18, 88, 8, '#334155')
  ;[92, 88, 96, 80, 94, 90, 60, 92, 84, 70].forEach((width, i) => {
    const y = 40 + i * 12
    if (i === 3) {
      c.globalAlpha = 0.85
      bar(12, y - 4, 104, 12, color)
      c.globalAlpha = 1
    }
    bar(16, y, width, 4, i === 3 ? '#475569' : '#e2e8f0')
  })
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 4
  textures.set(color, texture)
  return texture
}

let haloTexture: THREE.CanvasTexture | null = null
function halo(): THREE.CanvasTexture {
  if (haloTexture) return haloTexture
  const canvas = Object.assign(document.createElement('canvas'), { width: 64, height: 64 })
  const c = canvas.getContext('2d')!
  const g = c.createRadialGradient(32, 32, 0, 32, 32, 32)
  g.addColorStop(0, 'rgba(250, 204, 21, 0.9)')
  g.addColorStop(0.4, 'rgba(250, 204, 21, 0.35)')
  g.addColorStop(1, 'rgba(250, 204, 21, 0)')
  c.fillStyle = g
  c.fillRect(0, 0, 64, 64)
  haloTexture = new THREE.CanvasTexture(canvas)
  return haloTexture
}

/**
 * A paper as a page that always faces the camera, sized by its radius (its number of links). `faded`: out of the
 * current focus. `lit`: in focus while a paper is selected, so it sits in a soft yellow glow.
 */
export function paperObject(color: string, radius: number, faded: boolean, lit: boolean): THREE.Object3D {
  const group = new THREE.Group()
  const page = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: pageTexture(color), transparent: true, opacity: faded ? FADED : 1 }),
  )
  const height = radius * 4.4
  page.scale.set((height * PAGE.w) / PAGE.h, height, 1)
  group.add(page)
  if (lit) {
    const glow = new THREE.Sprite(
      new THREE.SpriteMaterial({ map: halo(), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }),
    )
    glow.scale.setScalar(height * 1.8)
    glow.renderOrder = -1
    group.add(glow)
  }
  return group
}

/** The app's --background as a three.js colour, whatever CSS colour syntax the theme uses (read back as a pixel). */
export function pageBackground(): THREE.Color {
  const css = getComputedStyle(document.documentElement).getPropertyValue('--background').trim() || '#f8fafc'
  const c = Object.assign(document.createElement('canvas'), { width: 1, height: 1 }).getContext('2d')!
  c.fillStyle = css
  c.fillRect(0, 0, 1, 1)
  const [r, g, b] = c.getImageData(0, 0, 1, 1).data
  return new THREE.Color().setRGB(r / 255, g / 255, b / 255, THREE.SRGBColorSpace)
}

/** Fog from the camera's distance outward, into the page's background, so far papers fade instead of cluttering. */
export function fogFor(distance: number): THREE.Fog {
  return new THREE.Fog(pageBackground(), distance * 0.9, distance * 2.4)
}
