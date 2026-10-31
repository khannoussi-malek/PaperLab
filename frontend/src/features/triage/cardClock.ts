/** Card and PDF time are capped so a card left open overnight doesn't read as a 9 hour look. */
const CARD_CAP_MS = 1_800_000

/** Times one card: card and PDF time run only while active (tab visible, window focused). */
export class CardClock {
  private active = true
  private pdfShown = false
  private opened = false
  private card = 0
  private pdf = 0
  private last: number

  private readonly now: () => number

  constructor(now: () => number = () => performance.now()) {
    this.now = now
    this.last = this.now()
  }

  private flush() {
    const t = this.now()
    if (this.active) {
      this.card += t - this.last
      if (this.pdfShown) this.pdf += t - this.last
    }
    this.last = t
  }

  setActive(on: boolean) { this.flush(); this.active = on }
  setPdfShown(on: boolean) { this.flush(); this.pdfShown = on }
  /** An interaction in the PDF column; showing the column is not one. */
  interact() { if (this.pdfShown) this.opened = true }

  read() {
    this.flush()
    return { card_ms: Math.min(this.card, CARD_CAP_MS), pdf_ms: Math.min(this.pdf, CARD_CAP_MS), pdf_opened: this.opened }
  }

  reset() {
    this.card = 0
    this.pdf = 0
    this.opened = false
    this.last = this.now()
  }
}
