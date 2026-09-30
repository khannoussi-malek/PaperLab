// What each section adds to the scene besides the page and the flying pages: the AI answer and its citation, the
// dome of your machine with the You and AI notes, the Claude tools, the pulse through the graph, and the mark's
// highlight. Each has a pose weight (0..1, from the scroll) and a moment (seconds since its section arrived).
import * as THREE from 'three'
import { clamp01, lerp, out, progress } from './ease'
import { C, PEN, answerTexture, card, chipTexture, claudeTexture, dotTexture, highlighter, noteTexture } from './paint'
import { fadeAll, flashAt } from './story'

const TOOLS = ['search_library', 'get_paper', 'related_papers', 'create_note']

// Arc from a to b that lifts toward the camera, u in 0..1.
const arc = (a: THREE.Vector3, b: THREE.Vector3, u: number, lift = 0.8) =>
  a.clone().lerp(b, u).add(new THREE.Vector3(0, Math.sin(u * Math.PI) * lift * 0.6, Math.sin(u * Math.PI) * lift))

export function extras(scene: THREE.Scene, bandPoint: THREE.Vector3, edges: THREE.CatmullRomCurve3[], graph: THREE.Group) {
  const glowTex = dotTexture()

  // Ask: the answer card beside the page; its [C1] flies onto the highlighted passage.
  const ask = new THREE.Group()
  const answer = card(answerTexture(), 3.0)
  answer.position.set(1.6, 1.3, 0.6)
  answer.rotation.set(-0.04, -0.3, 0.02)
  const c1From = new THREE.Vector3(0.2, 0.55, 0.05).applyEuler(answer.rotation).add(answer.position)
  const c1 = card(chipTexture('C1 · p. 4', { width: 420 }), 1.0)
  const bandFlash = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: C.yellow, transparent: true, depthWrite: false }))
  bandFlash.scale.set(3.4, 0.9, 1)
  bandFlash.position.copy(bandPoint)
  ask.add(answer, c1, bandFlash)
  scene.add(ask)

  // Rules: the library in a glass dome (your machine), the You note and the AI note kept apart outside it.
  const rules = new THREE.Group()
  const dome = new THREE.Mesh(
    new THREE.SphereGeometry(2.1, 64, 32),
    new THREE.MeshPhysicalMaterial({ color: '#dbeafe', roughness: 0.06, metalness: 0, clearcoat: 1, transparent: true, opacity: 0.18, depthWrite: false }),
  )
  ;(dome.material as THREE.Material).userData.alpha = 0.18
  const you = card(noteTexture(['Why 15%? Try 10% and', '20% on my runs.']), 2.3)
  you.position.set(-2.9, 1.7, 0.4)
  you.rotation.set(0, 0.25, 0.03)
  const ai = card(noteTexture(['Masking 15% keeps the', 'task hard. [C1]'], true), 2.3)
  ai.position.set(2.2, -1.9, 0.6)
  ai.rotation.set(0, -0.28, -0.03)
  rules.add(dome, you, ai)
  scene.add(rules)

  // Claude: four tool chips orbit the library, wired to the Claude card; create_note drops a note marked AI.
  const claude = new THREE.Group()
  const claudeCard = card(claudeTexture(), 2.0)
  claudeCard.position.set(0, 2.8, 0.2)
  const chips = TOOLS.map((name) => card(chipTexture(name, { mono: true, width: 520 }), 1.35))
  const threadMat = new THREE.LineBasicMaterial({ color: C.blue, transparent: true })
  ;(threadMat as THREE.Material).userData.alpha = 0.5
  const threads = chips.map(() => {
    const geo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()])
    return new THREE.Line(geo, threadMat)
  })
  const dropped = card(noteTexture(['A note Claude wrote,', 'marked AI.'], true), 2.0)
  claude.add(claudeCard, ...chips, ...threads, dropped)
  scene.add(claude)

  // Graph: a glow runs along every wire once when the section arrives.
  const pulses = edges.map(() => {
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: C.yellow, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }))
    s.scale.setScalar(0.35)
    graph.add(s)
    return s
  })

  // Open: the mark's highlight, swept when the last section arrives.
  const markPen = highlighter()
  const markBand = new THREE.Mesh(
    new THREE.PlaneGeometry(1.5 * (1 + (PEN.pad * 2) / PEN.w), 0.2 * (1 + (PEN.pad * 2) / PEN.h)),
    new THREE.MeshBasicMaterial({ map: markPen.tex, transparent: true, depthWrite: false, toneMapped: false }),
  )
  markBand.position.set(-0.05, 3.4 * 0.84 * 0.09, 0.05)
  scene.add(markBand)

  const tmp = new THREE.Vector3()
  /** w: pose weights per part; m: seconds since that part's section arrived (-1 before it has). */
  const update = (t: number, w: { ask: number; rules: number; claude: number; graph: number; open: number }, m: { ask: number; rules: number; claude: number; graph: number; open: number }) => {
    // Ask.
    const fly = out(progress(m.ask, 0.3, 0.9))
    c1.position.copy(arc(c1From, bandPoint, fly))
    c1.rotation.copy(answer.rotation)
    c1.scale.setScalar(lerp(1, 0.7, fly))
    ;(bandFlash.material as THREE.Material).userData.alpha = 0.8 * flashAt(m.ask, 1.25)
    answer.position.y = 1.3 + (1 - w.ask) * -0.8
    fadeAll(ask, w.ask)

    // Rules: the dome turns slowly, and spins a glint when the section arrives.
    dome.rotation.y = t * 0.1 + out(progress(m.rules, 0, 1.4)) * Math.PI * 2
    ;(dome.material as THREE.Material).userData.alpha = 0.18 + 0.25 * flashAt(m.rules, 0.4)
    you.position.x = -2.9 - (1 - w.rules) * 1.5
    ai.position.x = 2.2 + (1 - w.rules) * 1.5
    fadeAll(rules, w.rules)

    // Claude.
    chips.forEach((chip, i) => {
      const a = t * 0.35 + (i / chips.length) * Math.PI * 2
      chip.position.set(Math.cos(a) * 2.5, Math.sin(a * 2) * 0.35 - 0.2, Math.sin(a) * 1.6)
      const g = threads[i].geometry as THREE.BufferGeometry
      g.setFromPoints([chip.position, tmp.copy(claudeCard.position).setY(2.4)])
    })
    const drop = out(progress(m.claude, 0.4, 0.8))
    dropped.position.set(lerp(0.4, 1.5, drop), lerp(0.2, -2.2, drop), 1.2)
    dropped.scale.setScalar(lerp(0.3, 1, drop))
    dropped.visible = drop > 0.02
    fadeAll(claude, w.claude)
    dropped.visible = dropped.visible && w.claude > 0.01

    // Graph pulses.
    const run = progress(m.graph, 0.2, 1.6)
    pulses.forEach((s, i) => {
      s.position.copy(edges[i].getPoint(clamp01(run * 1.3 - (i % 5) * 0.06)))
      s.material.opacity = Math.sin(Math.PI * clamp01(run * 1.3 - (i % 5) * 0.06)) * w.graph
      s.visible = s.material.opacity > 0.01
    })

    // Open.
    markPen.paint(out(progress(m.open, 0.6, 0.8)) * w.open)
    markBand.visible = w.open > 0.01
  }
  return { update }
}
