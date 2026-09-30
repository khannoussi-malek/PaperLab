import * as THREE from 'three'
import type { ChartTheme } from '@/features/charts/palette'
import type { Emphasis } from './paperModel'

// What the 3D view adds on top of the library's spheres (loaded with react-force-graph-3d, never before): a yellow
// glow around the selected paper and a softer one around the papers it links to, and a name over each of them.

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

const LABEL = { font: 28, padX: 18, height: 52 } // canvas px, drawn at 2x
const INK: Record<ChartTheme, { card: string; text: string; border: string }> = {
  light: { card: '#ffffff', text: '#0f172a', border: '#cbd5e1' },
  dark: { card: '#1e293b', text: '#f1f5f9', border: '#475569' },
}

// A paper's name on a small card, always facing the camera and drawn over everything, so it's never hidden.
function label(text: string, selected: boolean, theme: ChartTheme): THREE.Sprite {
  const ink = INK[theme]
  const font = `${selected ? 700 : 500} ${LABEL.font}px "Atkinson Hyperlegible Next Variable", system-ui, sans-serif`
  const probe = document.createElement('canvas').getContext('2d')!
  probe.font = font
  const width = Math.ceil(probe.measureText(text).width) + LABEL.padX * 2
  const canvas = Object.assign(document.createElement('canvas'), { width: width * 2, height: LABEL.height * 2 })
  const c = canvas.getContext('2d')!
  c.scale(2, 2)
  c.fillStyle = ink.card
  c.strokeStyle = selected ? '#eab308' : ink.border
  c.lineWidth = selected ? 3 : 1.5
  c.beginPath()
  c.roundRect(2, 2, width - 4, LABEL.height - 4, 12)
  c.fill()
  c.stroke()
  c.fillStyle = ink.text
  c.font = font
  c.textBaseline = 'middle'
  c.fillText(text, LABEL.padX, LABEL.height / 2 + 1)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  // A fixed size on screen (no size attenuation), so a name stays readable however far the camera is: the scale is
  // a share of the view's height: about 26 px tall for the selected paper and 20 px for the others.
  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: texture, depthTest: false, transparent: true, sizeAttenuation: false }),
  )
  sprite.renderOrder = 10
  const screenHeight = selected ? 0.036 : 0.028
  sprite.scale.set((screenHeight * width) / LABEL.height, screenHeight, 1)
  return sprite
}

/**
 * The glow and name for one paper, added to its sphere (an empty group leaves the plain sphere). `name`: its short
 * title, when it is one of the papers named around the selection.
 */
export function emphasisObject(kind: Emphasis, name: string | null, radius: number, theme: ChartTheme): THREE.Object3D {
  const group = new THREE.Group()
  if (kind !== 'selected' && kind !== 'connected') return group
  const selected = kind === 'selected'
  const glow = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: halo(), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: selected ? 1 : 0.6 }),
  )
  glow.scale.setScalar(radius * (selected ? 6 : 4))
  group.add(glow)
  if (name) {
    const tag = label(name, selected, theme)
    tag.position.y = radius + (selected ? 6 : 5)
    group.add(tag)
  }
  return group
}
