// The pieces every 3D moment is built from: the stage, the logo mark (card, highlighter, glow, sheen, shadow), the
// dust that gathers into it, and the stream of flying pages. Each returns its object(s) and an update; the stage
// disposes everything under its scene.
import * as THREE from 'three'
import { lerp, seeded } from './clock'
import { C, beamTexture, dotTexture, glowTexture, outlineTexture, pageTexture, shadowTexture, strokeTexture } from './paint'
import { BAND_Y, MARK, markPoints } from './shape'

export type Stage = {
  scene: THREE.Scene
  camera: THREE.PerspectiveCamera
  render(): void
  resize(width: number, height: number): void
  /** Re-reads the page background into the fog (after a theme change). */
  refog(): void
  dispose(): void
}

const pageBackground = () =>
  new THREE.Color(getComputedStyle(document.documentElement).getPropertyValue('--background').trim() || '#f8fafc')

/** `renderer` is for tests only; the app always lets the stage make its own. */
export function stage(canvas: HTMLCanvasElement, renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true })): Stage {
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75))
  renderer.toneMapping = THREE.NoToneMapping // keeps the brand whites white
  const scene = new THREE.Scene()
  scene.fog = new THREE.Fog(pageBackground(), 10, 34)
  const camera = new THREE.PerspectiveCamera(42, 1, 0.05, 200)
  return {
    scene,
    camera,
    render: () => renderer.render(scene, camera),
    resize(width, height) {
      renderer.setSize(width, height, false)
      camera.aspect = width / Math.max(height, 1)
      camera.updateProjectionMatrix()
    },
    refog: () => void (scene.fog as THREE.Fog).color.copy(pageBackground()),
    dispose() {
      const textures = new Set<THREE.Texture>()
      scene.traverse((o) => {
        const mesh = o as THREE.Mesh
        mesh.geometry?.dispose()
        for (const m of [mesh.material ?? []].flat() as THREE.Material[]) {
          for (const value of Object.values(m)) if (value instanceof THREE.Texture) textures.add(value)
          m.dispose()
        }
      })
      textures.forEach((t) => t.dispose())
      scene.clear()
      renderer.dispose()
    },
  }
}

const basic = (params: THREE.MeshBasicMaterialParameters) =>
  new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false, toneMapped: false, ...params })

/** One page card (the flying pages' look). */
export function pageCard(width: number): THREE.Mesh {
  return new THREE.Mesh(new THREE.PlaneGeometry(width, width * (420 / 320)), basic({ map: pageTexture(true), side: THREE.DoubleSide }))
}

export type MarkState = { card: number; sweep: number; flash: number; sheen: number }

/** The logo: shadow, card, highlighter band, the line's flat glow and the sheen, drawn in that fixed order. */
export function logoMark() {
  const group = new THREE.Group()
  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(MARK.w * 1.45, MARK.h * 1.35), basic({ map: shadowTexture() }))
  shadow.position.set(0.18, -0.28, -0.35)
  const card = new THREE.Mesh(new THREE.PlaneGeometry(MARK.w, MARK.h), basic({ map: pageTexture(false), side: THREE.DoubleSide }))
  const bandW = MARK.w * (520 / 640)
  // The band grows from its left edge: its geometry starts at x = 0.
  const band = new THREE.Mesh(
    new THREE.PlaneGeometry(bandW, MARK.h * (66 / 840)).translate(bandW / 2, 0, 0),
    basic({ map: strokeTexture(), color: C.yellow, opacity: 0.75 }),
  )
  band.position.set(-bandW / 2, BAND_Y, 0.01)
  const glow = new THREE.Mesh(new THREE.PlaneGeometry(bandW * 1.15, MARK.h * 0.2), basic({ map: glowTexture() }))
  glow.position.set(0, BAND_Y, 0.02)
  // The sheen's beam (map) slides across while the card's outline (alphaMap) stays put: light over the page only.
  const beam = beamTexture()
  beam.center.set(0.5, 0.5)
  beam.rotation = -0.5
  const sheen = new THREE.Mesh(new THREE.PlaneGeometry(MARK.w, MARK.h), basic({ map: beam, alphaMap: outlineTexture(), color: '#fff8db' }))
  sheen.position.z = 0.03
  // A fixed order: sorting by distance would flip these flat layers as the mark leans.
  ;[shadow, card, band, glow, sheen].forEach((m, i) => {
    m.renderOrder = i
    group.add(m)
  })
  const mat = (m: THREE.Mesh) => m.material as THREE.MeshBasicMaterial

  const update = ({ card: shown, sweep, flash, sheen: across }: MarkState) => {
    mat(card).opacity = shown
    card.scale.setScalar(lerp(0.92, 1, shown))
    mat(shadow).opacity = shown
    band.scale.x = Math.max(sweep, 0.0001)
    band.visible = sweep > 0
    mat(glow).opacity = flash * 0.9 + shown * 0.12 // a faint warmth stays on the line after the flash
    glow.scale.x = lerp(0.7, 1.05, flash)
    beam.offset.x = lerp(0.6, -0.6, across)
    mat(sheen).opacity = shown * (across > 0 && across < 1 ? 0.85 : 0)
  }
  return { group, update }
}

/** `n` motes drifting in a wide field; `gather` 0..1 pulls them onto the logo outline. */
export function dustField(n: number, seed: number) {
  const rand = seeded(seed)
  const targets = markPoints(n, rand)
  const seeds = Array.from({ length: n }, () => [(rand() - 0.5) * 30, (rand() - 0.5) * 16, (rand() - 0.5) * 12 - 4] as const)
  const pos = new Float32Array(n * 3)
  const col = new Float32Array(n * 3)
  const tint = new THREE.Color()
  seeds.forEach((_, i) => tint.set(i % 5 === 0 ? C.yellow : i % 2 ? C.mutedD : C.line2).toArray(col, i * 3))
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3))
  const material = new THREE.PointsMaterial({ size: 0.06, map: dotTexture(), vertexColors: true, transparent: true, depthWrite: false })
  const points = new THREE.Points(geo, material)

  const update = (gather: number, t: number) => {
    seeds.forEach(([x, y, z], i) => {
      const [tx, ty, tz] = targets[i]
      pos[i * 3] = lerp(x + Math.sin(t * 0.4 + i) * 0.3, tx, gather)
      pos[i * 3 + 1] = lerp(((y + t * 0.12 + 8) % 16) - 8, ty, gather)
      pos[i * 3 + 2] = lerp(z, tz, gather)
    })
    geo.attributes.position.needsUpdate = true
  }
  return { points, update }
}

/** `n` page cards streaming toward the camera and tumbling, sharing one material. */
export function pageStream(n: number, seed: number) {
  const rand = seeded(seed)
  const group = new THREE.Group()
  const material = basic({ map: pageTexture(true), side: THREE.DoubleSide })
  const geometry = new THREE.PlaneGeometry(1.1, 1.1 * (420 / 320))
  const pages = Array.from({ length: n }, () => {
    const m = new THREE.Mesh(geometry, material)
    group.add(m)
    return { m, x: (rand() - 0.5) * 30, y: (rand() - 0.5) * 16, z0: rand() * 40, rx: rand() * 6, ry: rand() * 6, sp: 0.6 + rand() }
  })
  const update = (t: number, opacity: number) => {
    material.opacity = opacity
    for (const pg of pages) {
      pg.m.position.set(pg.x, pg.y, ((pg.z0 + t * 2.4 * pg.sp) % 40) - 42)
      pg.m.rotation.set(Math.sin(pg.rx + t * 0.7) * 0.5, Math.sin(pg.ry + t * 0.5) * 0.8, Math.sin(pg.rx + t) * 0.3)
    }
  }
  return { group, update }
}
