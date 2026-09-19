import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

/** A PNG's width and height, from its IHDR chunk. */
function pngSize(file: string): [number, number] {
  const png = readFileSync(file)
  return [png.readUInt32BE(16), png.readUInt32BE(20)]
}

describe('packaging', () => {
  it("has the installers' icon and the menu-bar template images", () => {
    expect(pngSize('build/icon.png')).toEqual([1024, 1024])
    expect(pngSize('build/trayTemplate.png')).toEqual([16, 16])
    expect(pngSize('build/trayTemplate@2x.png')).toEqual([32, 32])
  })
})
