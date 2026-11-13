import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import type { Page } from '@playwright/test'
import { ask, expect, pickChatModel, test } from './fixtures'

const QUESTION_WAV = fileURLToPath(new URL('./fixtures/question.wav', import.meta.url))
/** What `FakeSpeech` always hears (backend `SPEECH_PROVIDER=fake`). */
const HEARD = 'What does this paper say?'
const FAKE_ANSWER = 'Fake answer: the method is described here [C1].'
const VOICE_DOWN = "Voice is off. Turn it on in Settings → Voice."

test.beforeEach(async ({ page, llmConnection }) => {
  await pickChatModel(page, llmConnection.modelId)
})

/**
 * Replaces the microphone with the recorded question (about 3 s of speech, then silence to 11 s), so the app's own code runs
 * unchanged. `loop` repeats it: the question then comes again while the answer is still playing.
 */
async function fakeMicrophone(page: Page, loop: boolean) {
  const wav = (await readFile(QUESTION_WAV)).toString('base64')
  await page.addInitScript(
    ([data, repeat]) => {
      navigator.mediaDevices.getUserMedia = async () => {
        const context = new AudioContext()
        const bytes = Uint8Array.from(atob(data), (c) => c.charCodeAt(0))
        const source = context.createBufferSource()
        source.buffer = await context.decodeAudioData(bytes.buffer)
        source.loop = repeat
        const destination = context.createMediaStreamDestination()
        source.connect(destination)
        source.start()
        const track = destination.stream.getAudioTracks()[0]
        // The synthetic microphone has no echo to cancel; say it is cancelled, or the app turns talking over off.
        const real = track.getSettings.bind(track)
        track.getSettings = () => ({ ...real(), echoCancellation: true })
        return destination.stream
      }
    },
    [wav, loop] as const,
  )
}

async function openChat(page: Page, paperId: string) {
  await page.goto(`/#/papers/${paperId}?tab=chat`)
  await expect(page.getByRole('tab', { name: 'Chat' })).toHaveAttribute('aria-selected', 'true')
}

const savedAnswer = (page: Page) => page.locator('article.chat-answer[data-output-id]', { hasText: HEARD })

test('asking out loud shows the question and the cited answer, and saves it', async ({ page, paperId }) => {
  await fakeMicrophone(page, false)
  await openChat(page, paperId)

  await page.getByRole('button', { name: 'Ask out loud' }).click()
  await expect(page.getByText('Listening', { exact: true })).toBeVisible()

  const answer = savedAnswer(page)
  await expect(answer).toContainText(FAKE_ANSWER, { timeout: 45_000 })
  await expect(answer.locator('.chat-answer-footer')).toContainText('AI · ', { timeout: 45_000 })
  await expect(answer).not.toContainText('…') // all of it was heard, so all of it is saved
})

test('talking over an answer stops it and saves only what was heard', async ({ page, paperId }) => {
  await fakeMicrophone(page, true)
  await openChat(page, paperId)

  await page.getByRole('button', { name: 'Ask out loud' }).click()
  await expect(page.getByRole('button', { name: 'Speaking, press to turn off' })).toBeVisible({ timeout: 30_000 })

  // The question comes round again over the answer; the answer is cut off and saved with a mark.
  await expect(savedAnswer(page).first()).toContainText('…', { timeout: 45_000 })
  await page.getByRole('button', { name: /press to turn off/ }).click()
})

test("Settings shows the turn's numbers", async ({ page, paperId }) => {
  await fakeMicrophone(page, false)
  await openChat(page, paperId)
  await page.getByRole('button', { name: 'Ask out loud' }).click()
  await expect(savedAnswer(page).locator('.chat-answer-footer')).toContainText('AI · ', { timeout: 45_000 })

  await page.goto('/#/settings/voice')
  await expect(page.getByText('Voice is ready.')).toBeVisible()
  // The turn is in the cold or the warm table: some "Stop talking to first audio" row counts at least one turn.
  const rows = page.getByRole('row').filter({ has: page.getByRole('rowheader', { name: 'Stop talking to first audio' }) })
  await expect
    .poll(async () => Math.max(0, ...(await rows.locator('td:nth-child(2)').allTextContents()).map(Number)))
    .toBeGreaterThanOrEqual(1)
})

test('with voice off the button says where to turn it on, and typed chat still works', async ({ page, paperId }) => {
  await page.route('**/api/voice/status', (route) => route.fulfill({ json: { ready: false, stage: 'off', detail: VOICE_DOWN } }))
  await fakeMicrophone(page, false)
  await openChat(page, paperId)

  const button = page.getByRole('button', { name: 'Ask out loud' })
  await expect(button).toBeDisabled()
  await expect(button).toHaveAttribute('title', "Voice isn't running. Turn it on in Settings → Voice.")
  await expect(page.getByText('Listening', { exact: true })).toBeHidden()

  const answer = await ask(page, 'What is the method?')
  await expect(answer).toContainText('Fake answer')
})
