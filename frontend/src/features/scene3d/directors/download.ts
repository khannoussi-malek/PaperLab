// The search model download: dust gathers into the logo as the download runs; at done the card forms and the
// highlighter sweeps; on an error the dust drifts back out.
import { approach } from '../clock'
import { dustField, logoMark, pageStream, stage } from '../parts'
import { downloadPose, type DownloadInput } from '../poses'
import type { Director } from '../Scene3D'

const director: Director<DownloadInput> = (canvas) => {
  const s = stage(canvas)
  const mark = logoMark()
  const dust = dustField(500, 11)
  const pages = pageStream(18, 12)
  mark.group.add(dust.points)
  s.scene.add(mark.group, pages.group)
  s.camera.position.set(0, 0, 7.5)
  let gather = 0
  let doneAt: number | null = null
  return {
    resize: s.resize,
    refog: s.refog,
    dispose: s.dispose,
    frame(t, dt, input) {
      if (input.status === 'done') doneAt ??= t
      else doneAt = null
      const pose = downloadPose(input, doneAt === null ? 0 : t - doneAt)
      gather = approach(gather, pose.gather, dt) // the polled percent jumps every 2 s: glide to it
      dust.update(gather, t)
      mark.update(pose)
      mark.group.rotation.y = Math.sin(t * 0.4) * 0.12
      mark.group.position.y = Math.sin(t * 0.9) * 0.06
      pages.update(t, 0.5)
      s.render()
    },
  }
}
export default director
