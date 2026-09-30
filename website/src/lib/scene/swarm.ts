// The flying pages and the dust. Free, the pages stream toward the camera across the whole screen, as in the
// teaser; with a formation weight they gather into a citation graph or a tight cluster, and the dust gathers into
// the PaperLab mark. Weights come from the scroll (0 free, 1 formed), so scrolling back undoes them.
import * as THREE from 'three'
import { clamp01, lerp, seeded } from './ease'
import { C, canvasTexture, card, dotTexture, paintPage } from './paint'

const SWARM = 110
const DUST = 700
const GRAPH_NODES = 28
const GRAPH_EDGES = 2 // each node's nearest neighbours
const CLUSTER = 40

export interface SwarmPose {
  graph: number // 0..1: pages gather into the citation graph
  cluster: number // 0..1: pages pack into a ball (the library in the dome)
  mark: number // 0..1: dust draws the PaperLab mark
  fade: number // 0..1: how much of the swarm shows
}

// Points on a sphere shell, evenly spread (Fibonacci), so the graph reads as a globe of papers.
function shell(n: number, r: number) {
  return Array.from({ length: n }, (_, i) => {
    const y = 1 - (2 * (i + 0.5)) / n
    const a = i * 2.39996
    const s = Math.sqrt(1 - y * y)
    return new THREE.Vector3(Math.cos(a) * s * r, y * r * 0.8, Math.sin(a) * s * r)
  })
}

// The mark: a page outline and four text lines, as points (world units, centred).
function markPoints(n: number, rand: () => number, size = 3.4) {
  const out: THREE.Vector3[] = []
  const w = 0.62 * size, h = 0.84 * size
  for (let i = 0; i < n; i++) {
    const k = rand()
    let x: number, y: number
    if (k < 0.55) {
      const e = rand() * 2 * (w + h)
      if (e < w) [x, y] = [e - w / 2, h / 2]
      else if (e < w + h) [x, y] = [w / 2, h / 2 - (e - w)]
      else if (e < 2 * w + h) [x, y] = [w / 2 - (e - w - h), -h / 2]
      else [x, y] = [-w / 2, -h / 2 + (e - 2 * w - h)]
    } else {
      const line = Math.floor(rand() * 4)
      const len = line === 3 ? 0.4 : 0.7
      x = -w * 0.35 + rand() * w * len
      y = h * (0.28 - line * 0.19)
    }
    out.push(new THREE.Vector3(x, y, (rand() - 0.5) * 0.08))
  }
  return out
}

export function swarm(scene: THREE.Scene) {
  const rand = seeded(5)
  const tex = canvasTexture(320, 420, (c, w) => paintPage(c, w, true))
  const pages = Array.from({ length: SWARM }, () => {
    const m = card(tex, 1.1)
    m.material = (m.material as THREE.MeshBasicMaterial).clone()
    scene.add(m)
    return { m, x: (rand() - 0.5) * 34, y: (rand() - 0.5) * 18, z0: rand() * 40, rx: rand() * 6, ry: rand() * 6, sp: 0.6 + rand() }
  })

  // The graph: nodes on a shell and wires to each node's nearest neighbours, in one group that turns slowly.
  const nodes = shell(GRAPH_NODES, 3.2)
  const graph = new THREE.Group()
  const wireMat = new THREE.MeshPhysicalMaterial({ color: C.wire, roughness: 0.3, clearcoat: 1, transparent: true, opacity: 0 })
  const edges: THREE.CatmullRomCurve3[] = []
  nodes.forEach((a, i) => {
    const near = nodes.map((b, j) => ({ j, d: a.distanceTo(b) })).filter((e) => e.j > i).sort((p, q) => p.d - q.d)
    for (const { j } of near.slice(0, GRAPH_EDGES)) {
      const mid = a.clone().add(nodes[j]).multiplyScalar(0.55)
      const curve = new THREE.CatmullRomCurve3([a, mid, nodes[j]])
      edges.push(curve)
      graph.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 24, 0.018, 6, false), wireMat))
    }
  })
  scene.add(graph)

  const cluster = Array.from({ length: CLUSTER }, () =>
    new THREE.Vector3(rand() - 0.5, rand() - 0.5, rand() - 0.5).normalize().multiplyScalar(0.4 + rand() * 1.0),
  )

  // Dust, which can gather into the mark.
  const pos = new Float32Array(DUST * 3)
  const col = new Float32Array(DUST * 3)
  const c = new THREE.Color()
  const seeds = Array.from({ length: DUST }, (_, i) => {
    c.set(i % 5 === 0 ? C.yellow : i % 2 ? C.mutedD : C.line2).toArray(col, i * 3)
    return [(rand() - 0.5) * 34, (rand() - 0.5) * 16, (rand() - 0.5) * 14 - 3]
  })
  const mark = markPoints(DUST, rand)
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3))
  const dustMat = new THREE.PointsMaterial({ size: 0.05, map: dotTexture(), vertexColors: true, transparent: true, depthWrite: false })
  scene.add(new THREE.Points(geo, dustMat))

  const p = new THREE.Vector3()
  const update = (t: number, pose: SwarmPose) => {
    graph.rotation.y = t * 0.08
    wireMat.opacity = clamp01((pose.graph - 0.55) / 0.45) * pose.fade
    graph.visible = wireMat.opacity > 0.01
    pages.forEach((pg, i) => {
      p.set(pg.x, pg.y, ((pg.z0 + t * 2.4 * pg.sp) % 40) - 42)
      const g = i < GRAPH_NODES ? pose.graph : 0
      if (g > 0) p.lerp(nodes[i].clone().applyEuler(graph.rotation), g)
      const k = i < CLUSTER ? pose.cluster : 0
      if (k > 0) p.lerp(cluster[i].clone().applyAxisAngle(THREE.Object3D.DEFAULT_UP, t * 0.15), k)
      pg.m.position.copy(p)
      const settle = 1 - Math.max(g, k) * 0.85 // formed pages stop tumbling and face the camera
      pg.m.rotation.set(Math.sin(pg.rx + t * 0.7) * 0.5 * settle, Math.sin(pg.ry + t * 0.5) * 0.8 * settle, Math.sin(pg.rx + t) * 0.3 * settle)
      pg.m.scale.setScalar(lerp(1, 0.55, Math.max(g, k)))
      const formed = i < Math.max(g > 0 ? GRAPH_NODES : 0, k > 0 ? CLUSTER : 0)
      ;(pg.m.material as THREE.MeshBasicMaterial).opacity = pose.fade * (formed ? 1 : 1 - Math.max(pose.graph, pose.cluster) * 0.7)
    })
    seeds.forEach(([x, y, z], i) => {
      p.set(x + Math.sin(t * 0.4 + i) * 0.3, ((y + t * 0.12 + 8) % 16) - 8, z)
      if (pose.mark > 0) p.lerp(mark[i], pose.mark)
      pos.set([p.x, p.y, p.z], i * 3)
    })
    geo.attributes.position.needsUpdate = true
    dustMat.size = lerp(0.05, 0.075, pose.mark)
    dustMat.opacity = Math.max(pose.fade, pose.mark)
  }
  return { update, edges, graph }
}
