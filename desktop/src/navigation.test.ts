import { describe, expect, it } from 'vitest'
import { navigationFor, startupAction } from './navigation'

const APP = 'http://127.0.0.1:5190'
const STARTUP = 'file:///Applications/PaperLab.app/Contents/Resources/app.asar/src/startup.html'

describe('navigationFor', () => {
  it('keeps PaperLab and the startup page in the window', () => {
    expect(navigationFor(`${APP}/#/graph`, APP, STARTUP)).toBe('allow')
    expect(navigationFor(`${STARTUP}?action=retry`, APP, STARTUP)).toBe('allow')
  })

  it('sends any other web address to the system browser, another port on this computer too', () => {
    expect(navigationFor('https://doi.org/10.1000/xyz', APP, STARTUP)).toBe('external')
    expect(navigationFor('http://127.0.0.1:8000/', APP, STARTUP)).toBe('external')
    expect(navigationFor('http://localhost:5190/', APP, STARTUP)).toBe('external')
  })

  it('goes nowhere for other files, scripts, other schemes and garbage', () => {
    for (const url of ['file:///etc/passwd', 'javascript:alert(1)', 'mailto:a@b.c', 'not a url']) {
      expect(navigationFor(url, APP, STARTUP), url).toBe('deny')
    }
  })
})

describe('startupAction', () => {
  it("reads the startup page's buttons, and nothing else", () => {
    expect(startupAction(`${STARTUP}?action=retry`, STARTUP)).toBe('retry')
    expect(startupAction(`${STARTUP}?action=show-log`, STARTUP)).toBe('show-log')
    expect(startupAction(`${STARTUP}?action=rm`, STARTUP)).toBeNull()
    expect(startupAction(`${APP}/?action=retry`, STARTUP)).toBeNull()
  })
})
