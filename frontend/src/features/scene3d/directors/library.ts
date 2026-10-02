// The empty Library: the logo page floats in soft light, a sheen crossing it every few seconds; while PDFs upload,
// three cards fly in from the front and land on it.
import { lerp } from '../clock'
import { dustField, logoMark, pageCard, stage } from '../parts'
import { libraryPose, type LibraryInput } from '../poses'
import type { Director } from '../Scene3D'

const director: Director<LibraryInput> = (canvas) => {
  const s = stage(canvas)
  const mark = logoMark()
  const dust = dustField(120, 21)
  const cards = [0, 1, 2].map(() => pageCard(1.6))
  cards.forEach((c, i) => {
    c.renderOrder = 10 + i
    mark.group.add(c)
  })
  s.scene.add(mark.group, dust.points)
  s.camera.position.set(0, 0, 6.5)
  let since: number | null = null
  return {
    resize: s.resize,
    refog: s.refog,
    dispose: s.dispose,
    frame(t, _dt, { uploading }) {
      since = uploading ? (since ?? t) : null
      const pose = libraryPose(t, since === null ? null : t - since)
      mark.update({ card: 1, sweep: 1, flash: 0, sheen: pose.sheen })
      mark.group.rotation.set(Math.sin(t * 0.5) * 0.05, Math.sin(t * 0.35) * 0.35, 0)
      mark.group.position.y = Math.sin(t * 0.8) * 0.08
      cards.forEach((c, i) => {
        const k = pose.landed[i]
        c.visible = k > 0 && k < 1
        c.position.set(lerp(1.5 - i, 0.05 * i, k), lerp(-1.2, 0.04 * i, k), lerp(5, 0.06 + 0.02 * i, k))
        c.rotation.set(lerp(0.6, 0, k), lerp(-0.8, 0, k), lerp(0.4, 0, k))
      })
      dust.update(0, t)
      s.render()
    },
  }
}
export default director
