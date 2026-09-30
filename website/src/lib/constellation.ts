// The home hero in 3D: a small library of white pages floating in space, joined by citation wires, with a glow
// running along each wire from the paper that cites to the paper it cites. The camera leans toward the pointer and the
// whole library turns a little as the page scrolls. Brand rules hold: paper is white in both themes, yellow is the
// highlight, blue the citations, green and violet as on the site.
import * as THREE from 'three'

const COLORS = { yellow: '#facc15', green: '#4ade80', blue: '#60a5fa', wire: '#eab308', link: '#2563eb', dust: '#94a3b8' }
const HIGHLIGHTS = [COLORS.yellow, COLORS.green, COLORS.blue]

// Where each page floats: x, y, z, and a resting tilt. The first page is the one you are reading, in front.
const PAGES = [
  { at: [0, 0, 1.2], tilt: [-0.08, -0.28, 0.03], scale: 1.25 },
  { at: [-2.2, 1.3, -1.2], tilt: [0.1, 0.45, -0.06], scale: 0.9 },
  { at: [2.6, 1.6, -1.8], tilt: [-0.05, -0.55, 0.08], scale: 0.85 },
  { at: [-2.4, -1.5, -0.6], tilt: [0.12, 0.5, 0.05], scale: 0.8 },
  { at: [2.4, -1.4, -0.4], tilt: [0.04, -0.4, -0.07], scale: 0.9 },
  { at: [0.2, 2.6, -3.2], tilt: [0.2, 0.1, 0.04], scale: 0.75 },
  { at: [-0.6, -2.7, -2.6], tilt: [-0.15, 0.2, -0.05], scale: 0.7 },
]
// Who cites whom (page index pairs) and the wire's colour.
const CITATIONS: [number, number, string][] = [
  [0, 1, COLORS.wire], [0, 2, COLORS.link], [0, 4, COLORS.wire], [1, 3, COLORS.link],
  [2, 5, COLORS.wire], [4, 6, COLORS.link], [3, 6, COLORS.wire], [1, 5, COLORS.link],
]
const PAGE_W = 1.5
const PAGE_H = PAGE_W * 1.3
const DUST = 260

// A seeded random so every visit draws the same library.
function seeded(seed: number) {
  return () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646
}

function roundRect(c: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  c.beginPath()
  c.roundRect(x, y, w, h, r)
  c.fill()
}

// A white page with a title, grey lines and one or two highlighted lines, as on the drawn hero.
function pageTexture(rand: () => number, renderer: THREE.WebGLRenderer) {
  const w = 512, h = Math.round(512 * 1.3)
  const canvas = Object.assign(document.createElement('canvas'), { width: w, height: h })
  const c = canvas.getContext('2d')!
  c.fillStyle = '#ffffff'
  roundRect(c, 0, 0, w, h, 26)
  c.fillStyle = '#334155'
  roundRect(c, 52, 60, w * (0.5 + rand() * 0.3), 30, 12)
  const marked = new Set([2 + Math.floor(rand() * 5), 9 + Math.floor(rand() * 6)])
  for (let i = 0, y = 130; y < h - 60; i++, y += 38) {
    const lw = (w - 104) * (i % 7 === 6 ? 0.55 : 0.82 + rand() * 0.18)
    if (marked.has(i)) {
      c.fillStyle = HIGHLIGHTS[Math.floor(rand() * HIGHLIGHTS.length)] + 'aa'
      roundRect(c, 40, y - 10, lw + 24, 38, 8)
      c.fillStyle = '#94a3b8'
    } else c.fillStyle = '#e2e8f0'
    roundRect(c, 52, y, lw, 18, 9)
  }
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = renderer.capabilities.getMaxAnisotropy()
  return tex
}

// A soft round dot, drawn once, for the glows and the dust.
function glowTexture() {
  const canvas = Object.assign(document.createElement('canvas'), { width: 64, height: 64 })
  const c = canvas.getContext('2d')!
  const g = c.createRadialGradient(32, 32, 0, 32, 32, 32)
  g.addColorStop(0, 'rgba(255,255,255,1)')
  g.addColorStop(0.35, 'rgba(255,255,255,0.55)')
  g.addColorStop(1, 'rgba(255,255,255,0)')
  c.fillStyle = g
  c.fillRect(0, 0, 64, 64)
  return new THREE.CanvasTexture(canvas)
}

function makePages(renderer: THREE.WebGLRenderer, rand: () => number) {
  const geo = new THREE.PlaneGeometry(PAGE_W, PAGE_H)
  return PAGES.map((p, i) => {
    const map = pageTexture(rand, renderer)
    const mat = new THREE.MeshStandardMaterial({
      map, transparent: true, roughness: 0.85, side: THREE.DoubleSide,
      // Paper is white in both themes: a little self-light keeps it from reading grey in the shade.
      emissive: 0xffffff, emissiveMap: map, emissiveIntensity: 0.35,
    })
    const mesh = new THREE.Mesh(geo, mat)
    mesh.position.set(...(p.at as [number, number, number]))
    mesh.rotation.set(...(p.tilt as [number, number, number]))
    mesh.scale.setScalar(p.scale)
    mesh.userData = { base: mesh.position.clone(), tilt: mesh.rotation.clone(), phase: i * 1.7 }
    return mesh
  })
}

// A wire arcs out of the page plane so it reads as depth, not a flat line.
function wireCurve(a: THREE.Vector3, b: THREE.Vector3) {
  const mid = a.clone().add(b).multiplyScalar(0.5)
  mid.z += 1.1
  mid.y += 0.35
  return new THREE.QuadraticBezierCurve3(a.clone(), mid, b.clone())
}

function makeWires(pages: THREE.Mesh[], glow: THREE.Texture) {
  return CITATIONS.map(([from, to, color], i) => {
    const curve = wireCurve(pages[from].userData.base, pages[to].userData.base)
    const line = new THREE.Mesh(
      new THREE.TubeGeometry(curve, 48, 0.012, 6, false),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.55 }),
    )
    const pulse = new THREE.Sprite(
      new THREE.SpriteMaterial({ map: glow, color, blending: THREE.AdditiveBlending, depthWrite: false }),
    )
    pulse.scale.setScalar(0.32)
    return { line, pulse, curve, from, to, offset: i / CITATIONS.length, speed: 0.11 + (i % 3) * 0.03 }
  })
}

function makeDust(glow: THREE.Texture, rand: () => number) {
  const pos = new Float32Array(DUST * 3)
  for (let i = 0; i < DUST; i++) {
    pos.set([(rand() - 0.5) * 12, (rand() - 0.5) * 8, (rand() - 0.5) * 8 - 2], i * 3)
  }
  const geo = new THREE.BufferGeometry().setAttribute('position', new THREE.BufferAttribute(pos, 3))
  const mat = new THREE.PointsMaterial({
    map: glow, color: COLORS.dust, size: 0.07, transparent: true, opacity: 0.7, depthWrite: false,
  })
  return new THREE.Points(geo, mat)
}

/** Starts the scene on `canvas`, sized to its own box. Returns a stop function, or throws when WebGL is unavailable. */
export function startConstellation(canvas: HTMLCanvasElement) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.outputColorSpace = THREE.SRGBColorSpace
  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 60)
  scene.add(new THREE.HemisphereLight(0xffffff, 0x94a3b8, 2.2))
  const key = new THREE.DirectionalLight(0xffffff, 1.4)
  key.position.set(-3, 4, 6)
  scene.add(key)

  const rand = seeded(7)
  const glow = glowTexture()
  const library = new THREE.Group()
  const pages = makePages(renderer, rand)
  const wires = makeWires(pages, glow)
  const dust = makeDust(glow, rand)
  library.add(...pages, ...wires.flatMap((w) => [w.line, w.pulse]))
  scene.add(library, dust)

  const pointer = new THREE.Vector2()
  const lean = new THREE.Vector2()
  const onPointer = (e: PointerEvent) => pointer.set(e.clientX / innerWidth - 0.5, e.clientY / innerHeight - 0.5)
  window.addEventListener('pointermove', onPointer, { passive: true })

  const resize = () => {
    const { width, height } = canvas.getBoundingClientRect()
    renderer.setSize(width, height, false)
    camera.aspect = width / Math.max(height, 1)
    // ponytail: pull back on narrow boxes so the side pages stay in frame.
    camera.position.z = camera.aspect < 1 ? 11 : 9
    camera.updateProjectionMatrix()
  }
  const sizer = new ResizeObserver(resize)
  sizer.observe(canvas)

  const start = performance.now()
  const frame = () => {
    const t = (performance.now() - start) / 1000
    lean.lerp(pointer, 0.05)
    camera.position.x = lean.x * 2.2
    camera.position.y = -lean.y * 1.4
    camera.lookAt(0, 0, 0)
    library.rotation.y = Math.sin(t * 0.15) * 0.12 + Math.min(scrollY / 900, 1) * 0.6
    for (const page of pages) {
      const { base, tilt, phase } = page.userData
      page.position.y = base.y + Math.sin(t * 0.8 + phase) * 0.08
      page.rotation.x = tilt.x + Math.sin(t * 0.5 + phase) * 0.04
      page.rotation.y = tilt.y + Math.cos(t * 0.4 + phase) * 0.05
    }
    for (const w of wires) {
      const u = (t * w.speed + w.offset) % 1
      w.pulse.position.copy(w.curve.getPoint(u))
      w.pulse.material.opacity = Math.sin(u * Math.PI)
    }
    dust.rotation.y = t * 0.02
    renderer.render(scene, camera)
  }

  // Draw only while the hero is on screen.
  const seen = new IntersectionObserver(([entry]) => renderer.setAnimationLoop(entry.isIntersecting ? frame : null))
  seen.observe(canvas)

  return () => {
    seen.disconnect()
    sizer.disconnect()
    window.removeEventListener('pointermove', onPointer)
    renderer.setAnimationLoop(null)
    renderer.dispose()
  }
}
