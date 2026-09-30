// The film's stage: studio environment map, key and fill light, fog into the page's own background, and bloom on
// the few things brighter than white.
import * as THREE from 'three'
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js'
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js'
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js'
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js'
import { C } from './paint'

/** The site's --background, so far pages fade into the page itself (light or dark). */
export const pageBackground = () =>
  new THREE.Color(getComputedStyle(document.documentElement).getPropertyValue('--background').trim() || C.slate)

export function stage(canvas: HTMLCanvasElement) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true })
  // ponytail: capped at 1.75x pixels; the canvas spans the whole screen, and full 2x retina with bloom is heavy on
  // laptop GPUs. Raise it if the notes' text ever looks soft.
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75))
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
  // The bloom chain renders off-screen, where the canvas's own antialiasing does not apply: multisample it.
  const composer = new EffectComposer(renderer, new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: 4 }))
  const pass = new RenderPass(scene, camera)
  pass.clearAlpha = 0
  composer.addPass(pass)
  // Threshold just above white: only lights and flashes bloom; paper never hazes.
  composer.addPass(new UnrealBloomPass(new THREE.Vector2(1, 1), 0.7, 0.45, 1.02))
  composer.addPass(new OutputPass())
  return { renderer, scene, camera, composer, key }
}
