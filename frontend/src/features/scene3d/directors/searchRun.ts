// A workspace search run, in miniature: the logo breathes gently while sources are still being paged, settles calm
// once the run ends cleanly (exhausted or stopped), and its dust drifts back out on a failure. There's no percent
// to show here — unlike the model download, a search run has no "total expected" to divide by — so this never
// reads as a fill level, only as "something is happening."
import { approach } from '../clock'
import { dustField, logoMark, stage } from '../parts'
import { searchRunPose, type SearchRunStatus } from '../poses'
import type { Director } from '../Scene3D'

export type SearchRunInput = { status: SearchRunStatus }

const director: Director<SearchRunInput> = (canvas) => {
  const s = stage(canvas)
  const mark = logoMark()
  mark.update({ card: 1, sweep: 1, flash: 0, sheen: 0 }) // already formed: no intro to replay, just the breathing
  const dust = dustField(80, 7)
  mark.group.add(dust.points)
  s.scene.add(mark.group)
  s.camera.position.set(0, 0, 7)
  let gather = 0
  let scatter = 0
  return {
    resize: s.resize,
    refog: s.refog,
    dispose: s.dispose,
    frame(t, dt, { status }) {
      const pose = searchRunPose(status, t)
      gather = approach(gather, pose.gather, dt)
      scatter = approach(scatter, pose.scatter, dt)
      dust.update(gather - scatter * 0.3, t) // scatter pulls the dust back off the mark on a failure
      mark.update({ card: 1, sweep: 1, flash: 0, sheen: pose.sheen })
      mark.group.rotation.y = Math.sin(t * 0.4) * 0.1
      s.render()
    },
  }
}
export default director
