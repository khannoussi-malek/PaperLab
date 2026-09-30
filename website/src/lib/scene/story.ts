// The page you are reading, and what happens on it: the highlighter sweeps, a glossy yellow wire pulls a note off
// it, its light lands on the note, the page chip drops in. Ported from the brand teaser's chapters 2 and 3.
import * as THREE from 'three'
import { clamp01, lerp, out, progress } from './ease'
import { C, HIGHLIGHTS, PEN, canvasTexture, card, chipTexture, highlighter, noteTexture, paintPage, pageLineY, pill } from './paint'

export const PAGE_W = 3.2
const PAGE_H = 4.2
export const NOTE = { w: 2.6, h: 2.6 * (360 / 900) }
export const LOOP = 9 // seconds: highlight, wire, note, chip, hold, rewind
const LAND = 2.6 // when the wire's light lands on the note
const lineY = (i: number) => (0.5 - pageLineY(i) / 840) * PAGE_H
export const BAND = { x0: -1.3, w: 2.6, y: lineY(4), h: (66 / 840) * PAGE_H }
// The extra strokes of the highlight section: lines and their colours (the app's five, yellow already on line 4).
const STROKES = [
  { line: 1, color: HIGHLIGHTS[1], w: 0.92 },
  { line: 7, color: HIGHLIGHTS[2], w: 0.6 },
  { line: 9, color: HIGHLIGHTS[3], w: 0.9 },
  { line: 11, color: HIGHLIGHTS[4], w: 0.72 },
]

/** Sets the opacity of every material under `root` (they are all transparent). */
export function fadeAll(root: THREE.Object3D, alpha: number) {
  root.visible = alpha > 0.01
  root.traverse((o) => {
    const m = (o as THREE.Mesh).material as THREE.Material | undefined
    if (m) m.opacity = alpha * ((m.userData.alpha as number | undefined) ?? 1)
  })
}

function stroke(color: string, width: number, y: number) {
  const pen = highlighter(color)
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(BAND.w * (1 + (PEN.pad * 2) / PEN.w), BAND.h * (1 + (PEN.pad * 2) / PEN.h)),
    new THREE.MeshBasicMaterial({ map: pen.tex, transparent: true, depthWrite: false, toneMapped: false }),
  )
  mesh.scale.x = width
  mesh.position.set(BAND.x0 + (BAND.w * width) / 2, y, 0.02)
  return { mesh, paint: pen.paint }
}

// A soft yellow halo behind the note, lit when the wire lands while the dot swells. The note itself never goes past
// white: the bloom would blow the whole card out.
function noteGlow(width: number, height: number) {
  const pad = 60
  const tex = canvasTexture(900 + pad * 2, 360 + pad * 2, (c, w, h) => {
    c.shadowColor = C.yellow
    c.shadowBlur = 44
    c.fillStyle = C.yellow
    pill(c, pad, pad, w - pad * 2, h - pad * 2, 28)
  })
  const glow = new THREE.Mesh(
    new THREE.PlaneGeometry(width * (1 + (pad * 2) / 900), height * (1 + (pad * 2) / 360)),
    new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false, toneMapped: false }),
  )
  glow.position.z = -0.02
  return glow
}

// The glossy yellow wire from the highlight to the note, revealed from its start; a glowing dot rides its tip.
function wire(from: THREE.Vector3, to: THREE.Vector3) {
  const mid = from.clone().lerp(to, 0.5).add(new THREE.Vector3(1.2, -0.2, 0.8))
  const curve = new THREE.CatmullRomCurve3([from, mid, to])
  const segments = 300
  const radial = 16
  const geo = new THREE.TubeGeometry(curve, segments, 0.035, radial, false)
  const tube = new THREE.Mesh(
    geo,
    new THREE.MeshPhysicalMaterial({ color: C.wire, roughness: 0.28, metalness: 0.05, clearcoat: 1, clearcoatRoughness: 0.12, transparent: true }),
  )
  const yellow = new THREE.Color(C.yellow)
  const dot = new THREE.Mesh(
    new THREE.SphereGeometry(0.09, 32, 16),
    new THREE.MeshPhysicalMaterial({ color: yellow, emissive: yellow, emissiveIntensity: 2.2, roughness: 0.3, transparent: true }),
  )
  const draw = (p: number) => {
    geo.setDrawRange(0, Math.floor(p * segments) * radial * 6)
    tube.visible = dot.visible = p > 0
    return dot.position.copy(curve.getPointAt(clamp01(p)))
  }
  return { tube, dot, draw }
}

/** The landing flash: quick rise at `at`, slow fall; 0 outside. */
export const flashAt = (t: number, at: number) => progress(t, at - 0.1, 0.15) * (1 - out(progress(t, at + 0.05, 1.1)))

export function story(scene: THREE.Scene) {
  const page = new THREE.Group()
  page.add(card(canvasTexture(640, 840, (c, w) => paintPage(c, w, false), 2), PAGE_W))
  // The highlighted line is drawn darker, over the page (the painted page leaves it out); the strokes' lines are
  // already on the page.
  const line = new THREE.Mesh(
    new THREE.PlaneGeometry(2.4, (18 / 840) * PAGE_H),
    new THREE.MeshBasicMaterial({ color: C.muted, toneMapped: false, transparent: true }),
  )
  line.position.set(0, BAND.y, 0.01)
  page.add(line)
  const band = stroke(C.yellow, 1, BAND.y)
  const strokes = STROKES.map((s) => stroke(s.color, s.w, lineY(s.line)))
  page.add(band.mesh, ...strokes.map((s) => s.mesh))
  page.position.set(-0.9, -1.1, 0)
  page.rotation.set(-0.06, 0.28, 0)
  scene.add(page)
  page.updateMatrixWorld()

  const from = new THREE.Vector3(BAND.x0 + BAND.w, BAND.y, 0.02).applyMatrix4(page.matrixWorld)
  const noteEnd = new THREE.Vector3(0.1, 2.2, 0.9)
  const cable = wire(from, noteEnd)
  const note = card(noteTexture(['Why 15%? Try 10% and', '20% on my runs.']), NOTE.w)
  note.rotation.set(-0.05, -0.22, 0.04)
  const glow = noteGlow(NOTE.w, NOTE.h)
  const glowShade = glow.material as THREE.MeshBasicMaterial
  const chip = card(chipTexture('p. 4'), 0.9)
  chip.position.set(NOTE.w / 2 - 0.35, NOTE.h / 2 + 0.05, 0.03)
  note.add(glow, chip)
  const noteGroup = new THREE.Group()
  noteGroup.add(cable.tube, cable.dot, note)
  scene.add(noteGroup)
  // The wire lands on the middle of the note's left edge: this is where the note's centre sits from there.
  const toCentre = new THREE.Vector3(NOTE.w / 2, 0, 0).applyEuler(note.rotation)

  /**
   * u: time in the hero loop (seconds, 0..LOOP), or a fixed moment to hold. flash: an extra landing flash (0..1) a
   * section's moment can fire. strokes: 0..1, how far the highlight section's extra strokes have swept.
   */
  const update = (u: number, flash: number, strokesP: number) => {
    const keep = 1 - out(progress(u, LOOP - 1.2, 1))
    band.paint(out(progress(u, 0.3, 0.8)) * keep)
    strokes.forEach((s, i) => s.paint(out(clamp01(strokesP * 1.6 - i * 0.2))))
    const w = out(progress(u, 1.2, LAND - 1.2)) * keep
    const head = cable.draw(w)
    const scale = lerp(0.4, 1, w)
    note.scale.setScalar(scale)
    note.position.copy(head).addScaledVector(toCentre, scale)
    note.visible = w > 0.02
    const f = Math.max(flashAt(u, LAND), flash)
    const halo = progress(u, LAND - 0.1, 0.3) * keep
    glowShade.userData.alpha = 0.3 * halo + 0.45 * f
    cable.dot.scale.setScalar(1 + 0.9 * f)
    const c = out(progress(u, LAND + 0.35, 0.3)) * keep
    chip.position.y = NOTE.h / 2 + 0.05 + (1 - c) * 0.6
    chip.scale.setScalar(lerp(1.5, 1, c))
    chip.visible = c > 0.02
  }
  /** The band's point on the page, in world space (where a citation lands). */
  const bandPoint = new THREE.Vector3(0, BAND.y, 0.05).applyMatrix4(page.matrixWorld)
  return { page, noteGroup, update, bandPoint, bandMesh: band.mesh }
}
