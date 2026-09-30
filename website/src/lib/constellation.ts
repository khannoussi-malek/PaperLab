// The home hero in 3D, ported from the brand teaser's Three.js (videos/brand-teaser/kit/three.js and the scenes in
// videos/brand-teaser/index.html): white pages stream through the whole hero section, and on the picture's slot the
// page you are reading gets its highlight, a yellow wire pulls a note off it, and the note keeps its page. The film
// seeks a timeline; here the same scene loops live and the camera leans toward the pointer. The canvas is
// transparent and the fog fades into the page's own background, so it sits in both themes. Brand rules hold: paper is white, yellow is the
// one glow (bloom catches only colours brighter than white), blue is the page chip.
import * as THREE from 'three'
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js'
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js'
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js'
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js'

const C = {
  slate: '#0f172a', white: '#ffffff', ink: '#0f172a', muted: '#475569', mutedD: '#94a3b8',
  line: '#e2e8f0', line2: '#cbd5e1', title: '#334155', blue: '#2563eb', yellow: '#facc15', wire: '#eab308',
}
const FONT = '"Atkinson Hyperlegible Next Variable", system-ui, sans-serif'
const STORY_H = 6.8 // world units from the page's foot to the note's top, framed to fill the picture's slot
const LOOP = 9 // seconds: highlight, wire, note, chip, hold, rewind
const SWARM = 110
const DUST = 700
const PAGE_W = 3.2
const BAND = { x0: -1.3, w: 2.6, y: (0.5 - 407 / 840) * 4.2, h: (66 / 840) * 4.2 }

const clamp01 = (x: number) => Math.min(1, Math.max(0, x))
const progress = (t: number, at: number, len: number) => clamp01((t - at) / len)
const out = (x: number) => 1 - (1 - x) ** 3 // the app's ease-out
const lerp = (a: number, b: number, u: number) => a + (b - a) * u
function seeded(seed: number) {
  return () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646
}

function canvasTexture(w: number, h: number, paint: (c: CanvasRenderingContext2D, w: number, h: number) => void) {
  const canvas = Object.assign(document.createElement('canvas'), { width: w, height: h })
  paint(canvas.getContext('2d')!, w, h)
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 8
  return tex
}

function pill(c: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  c.beginPath()
  c.roundRect(x, y, w, h, r)
  c.fill()
}

// A paper page like the mark: title bar, text lines, and (for the swarm) the yellow band baked in.
function paintPage(c: CanvasRenderingContext2D, w: number, band: boolean) {
  const u = w / 640
  c.fillStyle = C.white
  c.strokeStyle = C.line2
  c.lineWidth = 3 * u
  c.beginPath()
  c.roundRect(2 * u, 2 * u, w - 4 * u, 836 * u, 44 * u)
  c.fill()
  c.stroke()
  const bar = (x: number, y: number, bw: number, bh: number, col: string) => {
    c.fillStyle = col
    pill(c, x * u, y * u, bw * u, bh * u, (bh / 2) * u)
  }
  bar(80, 90, 440, 36, C.title)
  const widths = [480, 470, 440, 480, 480, 460, 480, 300, 480, 450, 470, 360]
  widths.forEach((lw, i) => {
    const y = 190 + i * 52
    if (i !== 4) return bar(80, y, lw, 18, C.line)
    if (!band) return
    c.globalAlpha = 0.7
    bar(60, y - 24, 520, 66, C.yellow)
    c.globalAlpha = 1
    bar(80, y, 480, 18, C.muted)
  })
}

// An unlit card, so the brand's white stays white.
function card(tex: THREE.Texture, width: number) {
  const img = tex.image as HTMLCanvasElement
  return new THREE.Mesh(
    new THREE.PlaneGeometry(width, (width * img.height) / img.width),
    new THREE.MeshBasicMaterial({ map: tex, transparent: true, side: THREE.DoubleSide, toneMapped: false }),
  )
}

const noteTexture = () =>
  canvasTexture(900, 360, (c, w, h) => {
    c.fillStyle = C.white
    c.strokeStyle = C.line2
    c.lineWidth = 3
    c.beginPath()
    c.roundRect(2, 2, w - 4, h - 4, 28)
    c.fill()
    c.stroke()
    c.fillStyle = '#f1f5f9'
    pill(c, 44, 44, 150, 64, 32)
    c.fillStyle = C.ink
    c.textBaseline = 'middle'
    c.font = `700 36px ${FONT}`
    c.fillText('You', 82, 77)
    c.font = `400 44px ${FONT}`
    c.fillText('Why 15%? Try 10% and', 48, 180)
    c.fillText('20% on my runs.', 48, 240)
  })

const chipTexture = (text: string) =>
  canvasTexture(360, 110, (c, w, h) => {
    c.fillStyle = C.white
    c.strokeStyle = C.blue
    c.lineWidth = 5
    c.beginPath()
    c.roundRect(4, 4, w - 8, h - 8, 55)
    c.fill()
    c.stroke()
    c.fillStyle = C.blue
    c.font = `700 54px ${FONT}`
    c.textAlign = 'center'
    c.textBaseline = 'middle'
    c.fillText(text, w / 2, h / 2 + 2)
  })

// The page you are reading: a card, a band that sweeps on and glows, and the dark line in front of it.
function heroPage(scene: THREE.Scene) {
  const g = new THREE.Group()
  g.add(card(canvasTexture(640, 840, (c, w) => paintPage(c, w, false)), PAGE_W))
  const bandGeo = new THREE.BoxGeometry(BAND.w, BAND.h, 0.02).translate(BAND.w / 2, 0, 0)
  const band = new THREE.Mesh(bandGeo, new THREE.MeshBasicMaterial({ color: new THREE.Color(C.yellow).multiplyScalar(1.12) }))
  band.position.set(BAND.x0, BAND.y, 0.012)
  const line = new THREE.Mesh(
    new THREE.PlaneGeometry(2.4, (18 / 840) * 4.2),
    new THREE.MeshBasicMaterial({ color: C.muted, toneMapped: false }),
  )
  line.position.set(0, BAND.y + 0.012, 0.03)
  g.add(band, line)
  g.position.set(-0.9, -1.1, 0)
  g.rotation.set(-0.06, 0.28, 0)
  scene.add(g)
  g.updateMatrixWorld()
  const setBand = (p: number) => {
    band.scale.x = Math.max(0.0001, p)
    band.visible = p > 0
  }
  return { g, setBand }
}

// The glossy yellow wire from the highlight to the note, revealed from its start; a glowing dot rides its tip.
function wire(scene: THREE.Scene, from: THREE.Vector3, to: THREE.Vector3) {
  const mid = from.clone().lerp(to, 0.5).add(new THREE.Vector3(1.2, -0.2, 0.8))
  const curve = new THREE.CatmullRomCurve3([from, mid, to])
  const segments = 300
  const radial = 16
  const geo = new THREE.TubeGeometry(curve, segments, 0.035, radial, false)
  const tube = new THREE.Mesh(
    geo,
    new THREE.MeshPhysicalMaterial({ color: C.wire, roughness: 0.28, metalness: 0.05, clearcoat: 1, clearcoatRoughness: 0.12 }),
  )
  const yellow = new THREE.Color(C.yellow)
  const dot = new THREE.Mesh(
    new THREE.SphereGeometry(0.09, 32, 16),
    new THREE.MeshPhysicalMaterial({ color: yellow, emissive: yellow, emissiveIntensity: 2.2, roughness: 0.3 }),
  )
  scene.add(tube, dot)
  return (p: number) => {
    geo.setDrawRange(0, Math.floor(p * segments) * radial * 6)
    tube.visible = dot.visible = p > 0
    return dot.position.copy(curve.getPointAt(clamp01(p)))
  }
}

// White pages (the mark, with its band) streaming toward the camera through the fog, across the whole section,
// tumbling. They stop short of the hero page (z 0), so none crosses in front of the story.
function swarm(scene: THREE.Scene, rand: () => number) {
  const tex = canvasTexture(320, 420, (c, w) => paintPage(c, w, true))
  const pages = Array.from({ length: SWARM }, () => {
    const m = card(tex, 1.1)
    scene.add(m)
    return { m, x: (rand() - 0.5) * 34, y: (rand() - 0.5) * 18, z0: rand() * 40, rx: rand() * 6, ry: rand() * 6, sp: 0.6 + rand() }
  })
  return (t: number) => {
    for (const p of pages) {
      p.m.position.set(p.x, p.y, ((p.z0 + t * 2.4 * p.sp) % 40) - 42)
      p.m.rotation.set(Math.sin(p.rx + t * 0.7) * 0.5, Math.sin(p.ry + t * 0.5) * 0.8, Math.sin(p.rx + t) * 0.3)
    }
  }
}

// Soft dust drifting up, as in every slate chapter of the film.
function dust(scene: THREE.Scene, rand: () => number) {
  const pos = new Float32Array(DUST * 3)
  const col = new Float32Array(DUST * 3)
  const c = new THREE.Color()
  const seeds = Array.from({ length: DUST }, (_, i) => {
    c.set(i % 2 ? C.mutedD : C.line2).toArray(col, i * 3)
    return [(rand() - 0.5) * 34, (rand() - 0.5) * 16, (rand() - 0.5) * 14 - 3]
  })
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3))
  const sprite = canvasTexture(64, 64, (x) => {
    const g = x.createRadialGradient(32, 32, 0, 32, 32, 32)
    g.addColorStop(0, 'rgba(255,255,255,1)')
    g.addColorStop(0.45, 'rgba(255,255,255,.9)')
    g.addColorStop(1, 'rgba(255,255,255,0)')
    x.fillStyle = g
    x.fillRect(0, 0, 64, 64)
  })
  scene.add(new THREE.Points(geo, new THREE.PointsMaterial({ size: 0.05, map: sprite, vertexColors: true, transparent: true, depthWrite: false })))
  return (t: number) => {
    seeds.forEach(([x, y, z], i) => pos.set([x + Math.sin(t * 0.4 + i) * 0.3, ((y + t * 0.12 + 8) % 16) - 8, z], i * 3))
    geo.attributes.position.needsUpdate = true
  }
}

// The site's --background, so far pages fade into the page itself (light or dark).
const pageBackground = () =>
  new THREE.Color(getComputedStyle(document.documentElement).getPropertyValue('--background').trim() || C.slate)

// The film's stage: studio environment map, key and fill light, fog, and bloom on the few over-bright things.
function stage(canvas: HTMLCanvasElement) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true })
  // ponytail: bloom at 1.5x pixels at most; 2x doubles the GPU cost on retina for no visible gain.
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5))
  renderer.toneMapping = THREE.NoToneMapping // tone mapping greys the brand whites
  const scene = new THREE.Scene()
  scene.fog = new THREE.Fog(pageBackground(), 12, 36)
  scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture
  scene.environmentIntensity = 0.55
  scene.add(new THREE.HemisphereLight(0xffffff, C.slate, 0.5))
  const key = new THREE.DirectionalLight(0xffffff, 1.6)
  key.position.set(-4, 8, 6)
  scene.add(key)
  const camera = new THREE.PerspectiveCamera(42, 1, 0.05, 400)
  const composer = new EffectComposer(renderer)
  const pass = new RenderPass(scene, camera)
  pass.clearAlpha = 0
  composer.addPass(pass)
  composer.addPass(new UnrealBloomPass(new THREE.Vector2(1, 1), 0.8, 0.55, 1.0))
  composer.addPass(new OutputPass())
  return { renderer, scene, camera, composer }
}

/**
 * Starts the scene on `canvas` (the whole section), with the story centred on `anchor` (the picture's slot).
 * Resolves to a stop function; throws without WebGL.
 */
export async function startConstellation(canvas: HTMLCanvasElement, anchor: HTMLElement) {
  // The note and chip are painted with the site's font, so wait for it (a fallback font is fine if it fails).
  await document.fonts.load(`700 36px ${FONT}`).catch(() => undefined)
  const { renderer, scene, camera, composer } = stage(canvas)
  const rand = seeded(5)
  const streamPages = swarm(scene, rand)
  const drift = dust(scene, rand)
  const page = heroPage(scene)
  const from = new THREE.Vector3(BAND.x0 + BAND.w, BAND.y, 0.02).applyMatrix4(page.g.matrixWorld)
  const noteEnd = new THREE.Vector3(0.1, 2.3, 0.9)
  const drawWire = wire(scene, from, noteEnd)
  const note = card(noteTexture(), 2.6)
  const chip = card(chipTexture('p. 4'), 0.9)
  note.rotation.set(-0.05, -0.22, 0.04)
  chip.rotation.copy(note.rotation)
  scene.add(note, chip)

  // One loop: the band sweeps on, the wire pulls the note off it, the page chip lands, it holds, then rewinds.
  const story = (u: number) => {
    const keep = 1 - out(progress(u, LOOP - 1.2, 1))
    page.setBand(out(progress(u, 0.3, 0.8)) * keep)
    const w = out(progress(u, 1.2, 1.4)) * keep
    const head = drawWire(w)
    note.position.set(head.x + 0.9, head.y + 0.45, head.z)
    note.scale.setScalar(lerp(0.4, 1, w))
    note.visible = w > 0.02
    const c = out(progress(u, 2.8, 0.3)) * keep
    chip.position.set(noteEnd.x + 1.55, noteEnd.y - 0.1 + (1 - c) * 0.8, noteEnd.z + 0.05)
    chip.scale.setScalar(lerp(1.6, 1, c))
    chip.visible = c > 0.02
  }

  const pointer = new THREE.Vector2()
  const lean = new THREE.Vector2()
  const onPointer = (e: PointerEvent) => pointer.set(e.clientX / innerWidth - 0.5, e.clientY / innerHeight - 0.5)
  addEventListener('pointermove', onPointer, { passive: true })

  // The camera stands back far enough that the story (about STORY_H units tall) fills the anchor's height, and the
  // view is shifted so the story's centre lands on the anchor's centre; the rest of the section is open space.
  let radius = 10
  const resize = () => {
    const box = canvas.getBoundingClientRect()
    const slot = anchor.getBoundingClientRect()
    const width = Math.max(box.width, 1)
    const height = Math.max(box.height, 1)
    renderer.setSize(width, height, false)
    composer.setPixelRatio(renderer.getPixelRatio())
    composer.setSize(width, height)
    camera.aspect = width / height
    const fit = STORY_H * (height / Math.max(slot.height, 1))
    radius = fit / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)))
    scene.fog = new THREE.Fog(pageBackground(), radius + 2, radius + 34)
    const cx = slot.left + slot.width / 2 - box.left
    const cy = slot.top + slot.height / 2 - box.top
    camera.setViewOffset(width, height, width / 2 - cx, height / 2 - cy, width, height)
    camera.updateProjectionMatrix()
  }
  const sizer = new ResizeObserver(resize)
  sizer.observe(canvas)
  sizer.observe(anchor)
  // The theme can flip while the page is open; the fog follows it.
  const scheme = matchMedia('(prefers-color-scheme: dark)')
  scheme.addEventListener('change', resize)

  const target = new THREE.Vector3(0.4, 0.05, 0)
  const start = performance.now()
  const frame = () => {
    const t = (performance.now() - start) / 1000
    lean.lerp(pointer, 0.04)
    const az = THREE.MathUtils.degToRad(-8 + Math.sin(t * 0.18) * 7 + lean.x * 16)
    const el = THREE.MathUtils.degToRad(6 - lean.y * 10)
    const r = radius
    camera.position.set(target.x + r * Math.cos(el) * Math.sin(az), target.y + r * Math.sin(el), r * Math.cos(el) * Math.cos(az))
    camera.lookAt(target)
    streamPages(t)
    drift(t)
    story(t % LOOP)
    composer.render()
  }

  // Draw only while the hero is on screen.
  const seen = new IntersectionObserver(([entry]) => renderer.setAnimationLoop(entry.isIntersecting ? frame : null))
  seen.observe(canvas)

  return () => {
    seen.disconnect()
    sizer.disconnect()
    scheme.removeEventListener('change', resize)
    removeEventListener('pointermove', onPointer)
    renderer.setAnimationLoop(null)
    composer.dispose()
    renderer.dispose()
  }
}
