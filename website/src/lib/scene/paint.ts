// Everything the scene draws on 2D canvases and shows as textures: pages, notes, chips and cards, in the brand's
// colours and the site's font. Ported from the brand teaser (videos/brand-teaser/index.html).
import * as THREE from 'three'

export const C = {
  slate: '#0f172a', white: '#ffffff', ink: '#0f172a', muted: '#475569', mutedD: '#94a3b8',
  line: '#e2e8f0', line2: '#cbd5e1', title: '#334155', blue: '#2563eb', yellow: '#facc15', wire: '#eab308',
  ai: '#6d28d9', aiSurface: '#f5f3ff',
}
/** The app's five highlight colours (frontend/src/features/notes/highlightColors.ts). */
export const HIGHLIGHTS = ['#facc15', '#4ade80', '#60a5fa', '#f472b6', '#fb923c']
export const FONT = '"Atkinson Hyperlegible Next Variable", system-ui, sans-serif'
const MONO = 'ui-monospace, "SF Mono", Menlo, monospace'

type Paint = (c: CanvasRenderingContext2D, w: number, h: number) => void

// Painted at `sharp` times its size, so text and edges stay crisp up close; paint() still draws in w x h units.
export function canvasTexture(w: number, h: number, paint: Paint, sharp = 1) {
  const canvas = Object.assign(document.createElement('canvas'), { width: w * sharp, height: h * sharp })
  const c = canvas.getContext('2d')!
  c.scale(sharp, sharp)
  paint(c, w, h)
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 8
  return tex
}

export function pill(c: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  c.beginPath()
  c.roundRect(x, y, w, h, r)
  c.fill()
}

// A white card with the brand's thin border.
function paper(c: CanvasRenderingContext2D, w: number, h: number, r: number, border = C.line2) {
  c.fillStyle = C.white
  c.strokeStyle = border
  c.lineWidth = 3
  c.beginPath()
  c.roundRect(2, 2, w - 4, h - 4, r)
  c.fill()
  c.stroke()
}

// A paper page like the mark: title bar, text lines, and (for the swarm) the yellow band baked in.
export function paintPage(c: CanvasRenderingContext2D, w: number, band: boolean) {
  const u = w / 640
  c.fillStyle = C.white
  c.strokeStyle = C.line2
  c.lineWidth = 3 * u
  c.beginPath()
  c.roundRect(2 * u, 2 * u, w - 4 * u, 836 * u, 44 * u)
  c.fill()
  c.stroke()
  const bar = (x: number, y: number, bw: number, bh: number, col: string) => {
    c.fillStyle = col
    pill(c, x * u, y * u, bw * u, bh * u, (bh / 2) * u)
  }
  bar(80, 90, 440, 36, C.title)
  const widths = [480, 470, 440, 480, 480, 460, 480, 300, 480, 450, 470, 360]
  widths.forEach((lw, i) => {
    const y = 190 + i * 52
    if (i !== 4) return bar(80, y, lw, 18, C.line)
    if (!band) return
    c.globalAlpha = 0.7
    bar(60, y - 24, 520, 66, C.yellow)
    c.globalAlpha = 1
    bar(80, y, 480, 18, C.muted)
  })
}

/** The y (canvas px out of 840) of text line `i` on a painted page. */
export const pageLineY = (i: number) => 190 + i * 52 + 9

// An unlit card, so the brand's white stays white.
export function card(tex: THREE.Texture, width: number) {
  const img = tex.image as HTMLCanvasElement
  return new THREE.Mesh(
    new THREE.PlaneGeometry(width, (width * img.height) / img.width),
    new THREE.MeshBasicMaterial({ map: tex, transparent: true, side: THREE.DoubleSide, toneMapped: false }),
  )
}

// A note card: its badge ("You", or violet "✦ AI"), then its text, starting clear of the left edge where the
// wire's light lands.
export function noteTexture(lines: string[], ai = false) {
  return canvasTexture(900, 360, (c, w, h) => {
    paper(c, w, h, 28, ai ? '#ddd6fe' : C.line2)
    c.fillStyle = ai ? C.aiSurface : '#f1f5f9'
    pill(c, 80, 44, ai ? 170 : 150, 64, 32)
    c.fillStyle = ai ? C.ai : C.ink
    c.textBaseline = 'middle'
    c.font = `700 36px ${FONT}`
    c.fillText(ai ? '✦ AI' : 'You', 118, 77)
    c.fillStyle = C.ink
    c.font = `400 44px ${FONT}`
    lines.forEach((line, i) => c.fillText(line, 84, 180 + i * 60))
  }, 2)
}

// A rounded chip with coloured border and text: the page chip ("p. 4"), a citation ("C1 · p. 4"), a tool name.
export function chipTexture(text: string, { color = C.blue, mono = false, width = 360 } = {}) {
  return canvasTexture(width, 110, (c, w, h) => {
    c.fillStyle = C.white
    c.strokeStyle = color
    c.lineWidth = 5
    c.beginPath()
    c.roundRect(4, 4, w - 8, h - 8, 55)
    c.fill()
    c.stroke()
    c.fillStyle = color
    c.font = mono ? `600 44px ${MONO}` : `700 54px ${FONT}`
    c.textAlign = 'center'
    c.textBaseline = 'middle'
    c.fillText(text, w / 2, h / 2 + 2)
  }, 2)
}

// The AI answer from the Ask-a-paper feature: a violet badge, the answer with its citations, and the source chips.
export function answerTexture() {
  return canvasTexture(900, 520, (c, w, h) => {
    paper(c, w, h, 32, '#ddd6fe')
    c.fillStyle = C.aiSurface
    pill(c, 48, 44, 170, 64, 32)
    c.fillStyle = C.ai
    c.textBaseline = 'middle'
    c.font = `700 36px ${FONT}`
    c.fillText('✦ AI', 86, 77)
    c.fillStyle = C.ink
    c.font = `400 42px ${FONT}`
    const text = [['BERT learns from masked words ', '[C1]'], ['and next-sentence prediction ', '[C2]']]
    let y = 180
    for (const [plain, cite] of text) {
      c.fillStyle = C.ink
      c.fillText(plain, 52, y)
      const x = 52 + c.measureText(plain).width + 4
      c.fillStyle = C.blue
      c.font = `700 42px ${FONT}`
      c.fillText(cite, x, y)
      c.font = `400 42px ${FONT}`
      y += 62
    }
    c.font = `600 34px ${FONT}`
    for (const [i, chip] of ['C1 · p. 4', 'C2 · p. 5'].entries()) {
      const x = 52 + i * 220
      c.fillStyle = '#eff6ff'
      pill(c, x, 380, 196, 64, 32)
      c.fillStyle = C.blue
      c.fillText(chip, x + 26, 413)
    }
  }, 2)
}

// The Claude card for the MCP section: text only, no logo.
export function claudeTexture() {
  return canvasTexture(620, 300, (c, w, h) => {
    paper(c, w, h, 32)
    c.fillStyle = C.ink
    c.textBaseline = 'middle'
    c.font = `700 64px ${FONT}`
    c.fillText('Claude', 52, 110)
    c.fillStyle = C.muted
    c.font = `400 36px ${FONT}`
    c.fillText('Desktop · Code · any MCP', 52, 200)
  }, 2)
}

/** A highlighter stroke: a translucent pill drawn p of the way across (repaint as it sweeps, so the end stays round). */
export const PEN = { w: 1040, h: 66, pad: 26 } // canvas px: the stroke, and room around it for its glow
export function highlighter(color = C.yellow) {
  const w = PEN.w + PEN.pad * 2
  const h = PEN.h + PEN.pad * 2
  const canvas = Object.assign(document.createElement('canvas'), { width: w, height: h })
  const c = canvas.getContext('2d')!
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 8
  // Straight from the hex: THREE.Color would hand back linear values and turn the yellow orange.
  const n = parseInt(color.slice(1), 16)
  const rgba = (a: number) => `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a})`
  let drawn = -1
  const paint = (p: number) => {
    if (Math.abs(p - drawn) < 0.002) return
    drawn = p
    c.clearRect(0, 0, w, h)
    if (p > 0) {
      c.shadowColor = rgba(0.75)
      c.shadowBlur = 22
      c.fillStyle = rgba(0.8)
      pill(c, PEN.pad, PEN.pad, Math.max(PEN.h, PEN.w * p), PEN.h, PEN.h * 0.22)
    }
    tex.needsUpdate = true
  }
  return { tex, paint }
}

/** A soft round dot, for dust and glows. */
export const dotTexture = () =>
  canvasTexture(64, 64, (x) => {
    const g = x.createRadialGradient(32, 32, 0, 32, 32, 32)
    g.addColorStop(0, 'rgba(255,255,255,1)')
    g.addColorStop(0.45, 'rgba(255,255,255,.9)')
    g.addColorStop(1, 'rgba(255,255,255,0)')
    x.fillStyle = g
    x.fillRect(0, 0, 64, 64)
  })
