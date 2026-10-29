import { describe, expect, it } from 'vitest'
import { CardClock } from './cardClock'

function make() {
  let t = 0
  const clock = new CardClock(() => t)
  return { clock, tick: (ms: number) => { t += ms } }
}

describe('CardClock', () => {
  it('counts card time while active and pauses while inactive', () => {
    const { clock, tick } = make()
    tick(1000)
    clock.setActive(false)
    tick(5000)
    clock.setActive(true)
    tick(2000)
    expect(clock.read().card_ms).toBe(3000)
  })

  it('caps card time at 30 minutes', () => {
    const { clock, tick } = make()
    tick(3_600_000)
    expect(clock.read().card_ms).toBe(1_800_000)
  })

  it('counts pdf time only while active and shown', () => {
    const { clock, tick } = make()
    tick(1000)
    clock.setPdfShown(true)
    tick(2000)
    clock.setActive(false)
    tick(4000)
    clock.setActive(true)
    tick(500)
    clock.setPdfShown(false)
    tick(9000)
    expect(clock.read().pdf_ms).toBe(2500)
  })

  it('showing the pdf alone never sets pdf_opened', () => {
    const { clock, tick } = make()
    clock.setPdfShown(true)
    tick(60_000)
    expect(clock.read().pdf_opened).toBe(false)
  })

  it('an interaction while shown sets pdf_opened; while hidden it does not', () => {
    const hidden = make()
    hidden.clock.interact()
    hidden.clock.setPdfShown(true)
    expect(hidden.clock.read().pdf_opened).toBe(false)
    const shown = make()
    shown.clock.setPdfShown(true)
    shown.clock.interact()
    expect(shown.clock.read().pdf_opened).toBe(true)
  })

  it('reset zeroes the counters but keeps tracking', () => {
    const { clock, tick } = make()
    clock.setPdfShown(true)
    clock.interact()
    tick(1000)
    clock.reset()
    expect(clock.read()).toEqual({ card_ms: 0, pdf_ms: 0, pdf_opened: false })
    tick(250)
    expect(clock.read()).toEqual({ card_ms: 250, pdf_ms: 250, pdf_opened: false })
  })
})
