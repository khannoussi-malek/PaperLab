// @vitest-environment jsdom
import { beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  destroy: vi.fn(async () => {}),
  getUserMedia: vi.fn(),
  stopTrack: vi.fn(),
  settings: { echoCancellation: true } as MediaTrackSettings,
}))
vi.mock('@ricky0123/vad-web', () => ({ MicVAD: { new: mocks.create } }))

import { startMicrophone } from './microphone'

const stream = { getAudioTracks: () => [{ stop: mocks.stopTrack, getSettings: () => mocks.settings }], getTracks: () => [{ stop: mocks.stopTrack }] }
const handlers = () => ({ onFrame: vi.fn(), onSpeechStart: vi.fn(), onSpeechEnd: vi.fn() })
const start = (h = handlers()) => startMicrophone(h)

beforeEach(() => {
  vi.clearAllMocks()
  mocks.settings = { echoCancellation: true }
  mocks.getUserMedia.mockResolvedValue(stream)
  mocks.create.mockResolvedValue({ destroy: mocks.destroy })
  Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia: mocks.getUserMedia }, configurable: true })
})

it('asks for echo cancelling and loads the detector with the tuned options from the bundled assets', async () => {
  await start()
  expect(mocks.getUserMedia.mock.calls[0][0].audio).toMatchObject({ echoCancellation: true, channelCount: 1 })
  expect(mocks.create.mock.calls[0][0]).toMatchObject({
    model: 'v5',
    startOnLoad: true,
    baseAssetPath: '/voice/',
    onnxWASMBasePath: '/voice/',
    positiveSpeechThreshold: 0.5,
    negativeSpeechThreshold: 0.35,
    redemptionMs: 800,
    preSpeechPadMs: 300,
    minSpeechMs: 250,
  })
  expect(await mocks.create.mock.calls[0][0].getStream()).toBe(stream)
})

it('hands the detector’s events to the page', async () => {
  const h = handlers()
  await start(h)
  const options = mocks.create.mock.calls[0][0]
  const audio = new Float32Array(4)
  options.onFrameProcessed({ isSpeech: 0.9, notSpeech: 0.1 }, new Float32Array(512))
  options.onSpeechStart()
  options.onSpeechEnd(audio)
  expect(h.onFrame).toHaveBeenCalledWith(0.9)
  expect(h.onSpeechStart).toHaveBeenCalled()
  expect(h.onSpeechEnd).toHaveBeenCalledWith(audio)
})

it('reports whether the browser really cancels echo', async () => {
  expect((await start()).echoCancelled).toBe(true)
  mocks.settings = { echoCancellation: false }
  expect((await start()).echoCancelled).toBe(false)
})

it('says plainly when access is refused or there is no microphone, and loads nothing', async () => {
  mocks.getUserMedia.mockRejectedValueOnce(new DOMException('no', 'NotAllowedError'))
  await expect(start()).rejects.toThrow('Microphone access was refused. You can allow it in your system settings.')
  mocks.getUserMedia.mockRejectedValueOnce(new DOMException('none', 'NotFoundError'))
  await expect(start()).rejects.toThrow('No microphone was found.')
  expect(mocks.create).not.toHaveBeenCalled()
})

it('lets go of the microphone when the detector cannot load', async () => {
  mocks.create.mockRejectedValueOnce(new Error('missing model'))
  await expect(start()).rejects.toThrow('The microphone could not be started.')
  expect(mocks.stopTrack).toHaveBeenCalled()
})

it('stop destroys the detector and stops the track', async () => {
  const mic = await start()
  await mic.stop()
  expect(mocks.destroy).toHaveBeenCalled()
  expect(mocks.stopTrack).toHaveBeenCalled()
})
