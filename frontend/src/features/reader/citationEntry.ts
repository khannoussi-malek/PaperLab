import type { PdfRect } from './coords'

/**
 * Reading one numbered reference-list entry from a page's text (D144). Pure: `citations.ts` turns PDF.js's text items
 * into boxes, so every rule here runs on synthetic boxes in Vitest and on the real fixture PDF alike.
 */

/** One text item: its baseline-left point, right edge and height, in top-left PDF points. */
export type TextBox = { str: string; x0: number; x1: number; base: number; h: number }
/** One line of a column: its text (whitespace collapsed), its ink's left and right edges, baseline and height. */
export type Line = { text: string; x0: number; x1: number; base: number; h: number }
/** A page's text as columns of lines, left column first, each top to bottom. */
export type PageText = { page: number; width: number; columns: Line[][] }
/** `lines` as printed; `rects` one per line on the label's page, for the flash. */
export type Entry = { page: number; lines: string[]; text: string; rects: PdfRect[] }
/** Where a click on the citation scrolls and flashes: the entry's lines, or a strip at the destination. */
export type Jump = { page: number; rects: PdfRect[] }
/** A destination point in top-left PDF points. `x` is null when the link gave none (or 0): "either column". */
export type DestPoint = { x: number | null; y: number }
/** A `[N]` entry at the destination (`entry` null when over the caps), or null when there is no label: no citation. */
export type EntryAt = { label: number; entry: Entry | null; jump: Jump } | null

const MIDDLE_CROSSING_PT = 10 // a box crossing the page's middle by more than this on both sides spans the columns
const MAX_CROSSING_BOXES = 2 // ...and a page with at most this many such boxes has two columns
const SAME_LINE_PT = 1.5
const SAME_LINE_H = 0.3
const LINE_BREAK_PT = 12 // a horizontal gap wider than this ends a line (a sidebar or a stray gutter)
const WINDOW_ABOVE_H = 1
const WINDOW_BELOW_H = 2.5
const LABEL_INDENT_PT = 8
const ENTRY_GAP_H = 2.6
const MAX_CONTINUED_LINES = 6
const MAX_LINES = 12
const MAX_CHARS = 1200
const STRIP_PT = 12
const RECT_BELOW_H = 0.25
const LABEL = /^\[(\d{1,4})\]/

const hasInk = (box: TextBox) => box.str.trim() !== ''

/** The `N` of a line starting with `[N]`, else null. `N.` never counts: it matched years inside entries. */
export function labelOf(line: Pick<Line, 'text'>): number | null {
  const match = LABEL.exec(line.text)
  return match ? Number(match[1]) : null
}

/** Joins printed lines with a space, except after a trailing hyphen, which stays: the card never guesses. */
export const joinLines = (lines: string[]): string =>
  lines.reduce((text, line) => (text === '' ? line : text.endsWith('-') ? text + line : `${text} ${line}`), '')

/** Steps 1 and 2: the page's columns, each as lines top to bottom. */
export function pageColumns(boxes: TextBox[], width: number): Line[][] {
  const middle = width / 2
  const crossing = boxes.filter(
    (box) => hasInk(box) && box.x0 < middle - MIDDLE_CROSSING_PT && box.x1 > middle + MIDDLE_CROSSING_PT,
  )
  if (crossing.length > MAX_CROSSING_BOXES) return [linesOf(boxes)]
  const isLeft = (box: TextBox) => (box.x0 + box.x1) / 2 < middle
  return [linesOf(boxes.filter(isLeft)), linesOf(boxes.filter((box) => !isLeft(box)))]
}

function linesOf(boxes: TextBox[]): Line[] {
  const rows: TextBox[][] = []
  for (const box of [...boxes].sort((a, b) => a.base - b.base || a.x0 - b.x0)) {
    const row = rows.at(-1)
    const tolerance = Math.max(SAME_LINE_PT, SAME_LINE_H * Math.max(box.h, ...(row ?? []).map((b) => b.h)))
    if (row && Math.abs(box.base - row[0].base) <= tolerance) row.push(box)
    else rows.push([box])
  }
  return rows.map(lineOf).filter((line): line is Line => line !== null)
}

/** Boxes left to right, up to the first gap over LINE_BREAK_PT; null when the row holds no ink. */
function lineOf(row: TextBox[]): Line | null {
  const kept: TextBox[] = []
  let inkEnd: number | null = null
  for (const box of [...row].sort((a, b) => a.x0 - b.x0)) {
    if (hasInk(box)) {
      if (inkEnd !== null && box.x0 - inkEnd > LINE_BREAK_PT) break
      inkEnd = Math.max(inkEnd ?? box.x1, box.x1)
    }
    kept.push(box)
  }
  const ink = kept.filter(hasInk)
  if (ink.length === 0 || inkEnd === null) return null
  const text = kept.map((box) => box.str).join('').replace(/\s+/g, ' ').trim()
  return { text, x0: ink[0].x0, x1: inkEnd, base: ink[0].base, h: Math.max(...ink.map((box) => box.h)) }
}

/** Step 3: the first `[N]` line in the window, in the destination's column (both columns, nearest wins, without x). */
function findLabel(text: PageText, { x, y }: DestPoint): { column: number; index: number } | null {
  const { columns, width } = text
  const searched = columns.length === 1 ? [0] : x === null ? [0, 1] : [x < width / 2 ? 0 : 1]
  const found = searched.flatMap((column) => {
    const index = columns[column].findIndex(
      (line) => labelOf(line) !== null && line.base >= y - WINDOW_ABOVE_H * line.h && line.base <= y + WINDOW_BELOW_H * line.h,
    )
    return index === -1 ? [] : [{ column, index, distance: Math.abs(columns[column][index].base - y) }]
  })
  const nearest = found.sort((a, b) => a.distance - b.distance)[0]
  return nearest ? { column: nearest.column, index: nearest.index } : null
}

/** Step 4: the label line and the lines below it, up to the next label at its indent, a wide gap or the column's end. */
function walkDown(column: Line[], index: number): { lines: Line[]; endedAtLabel: boolean } {
  const label = column[index]
  const lines = [label]
  for (const line of column.slice(index + 1)) {
    if (labelOf(line) !== null && Math.abs(line.x0 - label.x0) <= LABEL_INDENT_PT) return { lines, endedAtLabel: true }
    if (line.base - lines[lines.length - 1].base > ENTRY_GAP_H * label.h) return { lines, endedAtLabel: false }
    lines.push(line)
  }
  return { lines, endedAtLabel: false }
}

/** Step 5: the lines just above `[N+1]` in the next column (right column, else the next page's first). */
function continuation(target: Line[] | undefined, label: number, h: number): Line[] {
  const at = target?.findIndex((line) => labelOf(line) === label + 1) ?? -1
  if (!target || at === -1) return []
  const above: Line[] = []
  for (let i = at - 1; i >= 0 && above.length < MAX_CONTINUED_LINES; i--) {
    const below = above[0] ?? target[at]
    if (below.base - target[i].base > ENTRY_GAP_H * h) break
    above.unshift(target[i])
  }
  return above
}

const lineRect = (line: Line): PdfRect => [line.x0, line.base - line.h, line.x1, line.base + RECT_BELOW_H * line.h]

/**
 * D144: the entry a link's destination points at. `here` is the destination's page, `next` the page after it (null
 * on the last page). Null when no `[N]` line sits in the window: the link is not a citation.
 */
export function entryAt(here: PageText, next: PageText | null, point: DestPoint): EntryAt {
  const found = findLabel(here, point)
  if (!found) return null
  const column = here.columns[found.column]
  const labelLine = column[found.index]
  const label = labelOf(labelLine)!
  const { lines, endedAtLabel } = walkDown(column, found.index)
  const inLeft = found.column === 0 && here.columns.length === 2
  const target = inLeft ? here.columns[1] : next?.columns[0]
  const continued = endedAtLabel ? [] : continuation(target, label, labelLine.h)
  const printed = [...lines, ...continued].map((line) => line.text)
  const text = joinLines(printed)
  if (printed.length > MAX_LINES || text.length > MAX_CHARS) {
    const x0 = Math.min(...column.map((line) => line.x0))
    const x1 = Math.max(...column.map((line) => line.x1))
    return { label, entry: null, jump: { page: here.page, rects: [[x0, point.y, x1, point.y + STRIP_PT]] } }
  }
  const onPage = inLeft ? [...lines, ...continued] : lines
  const entry = { page: here.page, lines: printed, text, rects: onPage.map(lineRect) }
  return { label, entry, jump: { page: entry.page, rects: entry.rects } }
}
