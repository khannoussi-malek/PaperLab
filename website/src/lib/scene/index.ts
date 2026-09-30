// The home page's scroll scene: one Three.js stage fixed behind the whole page. Every section marks itself with
// data-scene; as you scroll, each object blends between the poses of the sections around you (scrolling back plays
// it backwards), and when a section arrives its moment plays once. See docs/superpowers/specs (local) for the story.
import * as THREE from 'three'
import { extras } from './extras'
import { blendAt, sceneIndex } from './scroll'
import { pageBackground, stage } from './stage'
import { LOOP, fadeAll, flashAt, story } from './story'
import { swarm } from './swarm'
import { FONT } from './paint'

type Kind = 'hero' | 'highlight' | 'ask' | 'graph' | 'rules' | 'claude' | 'ambient' | 'open'
interface Pose {
  page: number; note: number; strokes: number; ask: number; rules: number; claude: number; open: number
  graph: number; cluster: number; mark: number; fade: number
  fit: number // world units framed in the anchor's height
  tx: number; ty: number // where the camera looks
  az: number; el: number // camera angle (degrees)
}
const base: Pose = {
  page: 0, note: 0, strokes: 0, ask: 0, rules: 0, claude: 0, open: 0, graph: 0, cluster: 0, mark: 0, fade: 1,
  fit: 7, tx: 0, ty: 0, az: 0, el: 6,
}
const POSES: Record<Kind, Pose> = {
  hero: { ...base, page: 1, note: 1, fit: 6.8, tx: 0.4, ty: 0.05, az: -8 },
  highlight: { ...base, page: 1, note: 1, strokes: 1, fade: 0.7, fit: 6, tx: -0.5, ty: -0.2, az: 14, el: 4 },
  ask: { ...base, page: 1, ask: 1, fade: 0.7, fit: 7, tx: 0.5, ty: 0.1, az: -12 },
  graph: { ...base, graph: 1, fit: 8.6, az: 0, el: 10 },
  rules: { ...base, rules: 1, cluster: 1, fit: 7.4, az: 6 },
  claude: { ...base, claude: 1, cluster: 1, fit: 7.6, ty: 0.3, az: -10 },
  ambient: { ...base, fade: 0.35, fit: 8 },
  open: { ...base, open: 1, mark: 1, fade: 0, fit: 6, el: 2 },
}
const KEYS = Object.keys(base) as (keyof Pose)[]
// The part of each section whose moment clock the extras read.
const MOMENTS = ['ask', 'rules', 'claude', 'graph', 'open'] as const

/**
 * Starts the scene on `canvas` (fixed, full screen). `slot` is the hero picture's place: the hero's story sits on
 * it and scrolls away with it. Resolves to a stop function; throws without WebGL.
 */
export async function startScene(canvas: HTMLCanvasElement, slot: HTMLElement) {
  // The notes and chips are painted with the site's font, so wait for it (a fallback font is fine if it fails).
  await document.fonts.load(`700 36px ${FONT}`).catch(() => undefined)
  const { renderer, scene, camera, composer } = stage(canvas)
  const flock = swarm(scene)
  const tale = story(scene)
  const more = extras(scene, tale.bandPoint, flock.edges, flock.graph)
  const sections = [...document.querySelectorAll<HTMLElement>('[data-scene]')]
  const kinds = sections.map((el) => (el.dataset.scene as Kind) in POSES ? (el.dataset.scene as Kind) : 'ambient')
  const values = Object.fromEntries(KEYS.map((k) => [k, kinds.map((kind) => POSES[kind][k])])) as Record<keyof Pose, number[]>

  const pointer = new THREE.Vector2()
  const lean = new THREE.Vector2()
  const onPointer = (e: PointerEvent) => pointer.set(e.clientX / innerWidth - 0.5, e.clientY / innerHeight - 0.5)
  addEventListener('pointermove', onPointer, { passive: true })

  const resize = () => {
    renderer.setSize(innerWidth, innerHeight, false)
    composer.setPixelRatio(renderer.getPixelRatio())
    composer.setSize(innerWidth, innerHeight)
    camera.aspect = innerWidth / Math.max(innerHeight, 1)
  }
  resize()
  addEventListener('resize', resize)
  const scheme = matchMedia('(prefers-color-scheme: dark)')
  const refog = () => (scene.fog as THREE.Fog).color.copy(pageBackground())
  scheme.addEventListener('change', refog)

  // Where on screen the subject sits: on the hero's slot while it is there, then the right column (desktop) or the
  // lower middle (phones), blended by the scroll like everything else.
  const anchorOf = (kind: Kind) => {
    if (kind === 'hero') {
      const r = slot.getBoundingClientRect()
      return { x: r.left + r.width / 2, y: r.top + r.height / 2, h: r.height }
    }
    const wide = innerWidth > 880
    return wide ? { x: innerWidth * 0.73, y: innerHeight * 0.52, h: innerHeight * 0.72 } : { x: innerWidth / 2, y: innerHeight * 0.6, h: innerHeight * 0.5 }
  }

  const started = new Map<number, number>() // section index → when its moment started (seconds)
  let lastWhole = -1
  const start = performance.now()
  const target = new THREE.Vector3()
  const frame = () => {
    const t = (performance.now() - start) / 1000
    // Section centres and the viewport's, re-read every frame, so resizes and jumps just work.
    const rects = sections.map((el) => el.getBoundingClientRect())
    const index = sceneIndex(rects.map((r) => r.top + r.height / 2), innerHeight / 2)
    const at = (k: keyof Pose) => blendAt(values[k], index)
    const whole = Math.round(index)
    if (whole !== lastWhole) started.set(whole, t)
    lastWhole = whole
    const since = (kind: Kind) => {
      const i = kinds.indexOf(kind)
      // Not arrived yet: -1, so its moment shows its starting state.
      return i >= 0 && started.has(i) ? t - started.get(i)! : -1
    }

    // Camera: frame `fit` world units in the anchor's height, looking at the pose's target, shifted so the target
    // lands on the anchor.
    const anchors = kinds.map(anchorOf)
    const ax = blendAt(anchors.map((a) => a.x), index)
    const ay = blendAt(anchors.map((a) => a.y), index)
    const ah = blendAt(anchors.map((a) => a.h), index)
    const radius = (at('fit') * (innerHeight / Math.max(ah, 1))) / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)))
    const fog = scene.fog as THREE.Fog
    fog.near = radius + 2
    fog.far = radius + 34
    lean.lerp(pointer, 0.04)
    const az = THREE.MathUtils.degToRad(at('az') + Math.sin(t * 0.18) * 7 + lean.x * 16)
    const el = THREE.MathUtils.degToRad(at('el') - lean.y * 10)
    target.set(at('tx'), at('ty'), 0)
    camera.position.set(target.x + radius * Math.cos(el) * Math.sin(az), target.y + radius * Math.sin(el), radius * Math.cos(el) * Math.cos(az))
    camera.lookAt(target)
    camera.setViewOffset(innerWidth, innerHeight, innerWidth / 2 - ax, innerHeight / 2 - ay, innerWidth, innerHeight)
    camera.updateProjectionMatrix()

    // The hero loops its story; later sections hold it at its finished state and replay the landing as a moment.
    const u = index < 0.5 ? t % LOOP : 4
    tale.update(u, index < 0.5 ? 0 : flashAt(since('highlight'), 0.3), at('strokes'))
    fadeAll(tale.page, at('page'))
    fadeAll(tale.noteGroup, at('note'))
    flock.update(t, { graph: at('graph'), cluster: at('cluster'), mark: at('mark'), fade: at('fade') })
    const w = { ask: at('ask'), rules: at('rules'), claude: at('claude'), graph: at('graph'), open: at('open') }
    const m = Object.fromEntries(MOMENTS.map((k) => [k, since(k)])) as typeof w
    more.update(t, w, m)

    // Past the last section the scene fades out, so the footer sits on the plain page.
    const last = rects[rects.length - 1]
    const shown = last ? Math.min(1, Math.max(0, last.bottom / (innerHeight * 0.6))) : 1
    canvas.style.opacity = String(shown)
    if (shown > 0) composer.render() // on the footer nothing shows: skip the bloom chain
  }
  renderer.setAnimationLoop(frame)

  return () => {
    removeEventListener('pointermove', onPointer)
    removeEventListener('resize', resize)
    scheme.removeEventListener('change', refog)
    renderer.setAnimationLoop(null)
    composer.dispose()
    renderer.dispose()
  }
}
