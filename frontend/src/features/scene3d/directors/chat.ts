// Waiting for an answer: a small page, a glossy yellow wire lifting off its highlighted line and pulling a note up,
// the light landing on the note. Ported from the brand teaser's wire moment, small enough for a chat bubble.
import * as THREE from 'three'
import { lerp } from '../clock'
import { C } from '../paint'
import { logoMark, pageCard, stage } from '../parts'
import { chatPose, type ChatInput } from '../poses'
import type { Director } from '../Scene3D'
import { BAND_Y, MARK } from '../shape'

const director: Director<ChatInput> = (canvas) => {
  const s = stage(canvas)
  const mark = logoMark()
  mark.update({ card: 1, sweep: 1, flash: 0, sheen: 0 })
  mark.group.position.set(-1.4, 0, 0)
  const note = pageCard(1.1)
  const from = new THREE.Vector3(-1.4 + (MARK.w * 520) / 640 / 2, BAND_Y, 0.05)
  const to = new THREE.Vector3(1.5, 0.2, 0.3)
  const curve = new THREE.CatmullRomCurve3([from, new THREE.Vector3(0.2, 1.2, 0.6), to])
  const tube = new THREE.TubeGeometry(curve, 48, 0.035, 8, false)
  const wire = new THREE.Mesh(tube, new THREE.MeshBasicMaterial({ color: C.wire, transparent: true, toneMapped: false }))
  const count = tube.index!.count
  s.scene.add(mark.group, wire, note)
  s.camera.position.set(0, 0.2, 6)
  return {
    resize: s.resize,
    refog: s.refog,
    dispose: s.dispose,
    frame(t, _dt, { phase }) {
      const k = chatPose(phase, t)
      tube.setDrawRange(0, Math.floor((count * k.wire) / 3) * 3)
      ;(wire.material as THREE.MeshBasicMaterial).opacity = k.fade
      note.position.set(to.x, lerp(-0.6, to.y, k.note), to.z)
      note.scale.setScalar(lerp(0.4, 1, k.note))
      note.visible = k.note > 0.01
      ;(note.material as THREE.MeshBasicMaterial).opacity = k.fade
      mark.update({ card: 1, sweep: 1, flash: k.light, sheen: 0 })
      mark.group.rotation.y = Math.sin(t * 0.6) * 0.15
      s.render()
    },
  }
}
export default director
