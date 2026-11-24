import { useCallback, useEffect, useRef, useState } from 'react'
import { useKeptTexts } from '@/features/manuscripts/keptTexts'
import { useLeaveWarning } from '@/features/manuscripts/useLeaveWarning'
import type { SaveState } from '@/features/manuscripts/autosave'

/** Save states of the open files, the leave warning while one is unsaved, and the flush the studio runs before it moves on. */
export function useUnsavedTexts(manuscriptId: string) {
  const kept = useKeptTexts(manuscriptId) // text a closed file could not save; lives outside the page
  const [saveStates, setSaveStates] = useState<Record<string, SaveState>>({})
  const [savedTick, setSavedTick] = useState(0) // bumps when a save settles, not when a file is opened
  const prevStates = useRef<Record<string, SaveState>>({})
  useEffect(() => {
    const settled = Object.entries(saveStates).some(([p, s]) => s === 'saved' && prevStates.current[p] !== undefined && prevStates.current[p] !== 'saved')
    prevStates.current = saveStates
    if (settled) setSavedTick((t) => t + 1)
  }, [saveStates])
  const flushRef = useRef<(() => Promise<boolean>) | null>(null)
  useLeaveWarning(Object.values(saveStates).some((s) => s !== 'saved')) // kept texts are warned about in App
  const flushCurrent = useCallback(async () => (await flushRef.current?.()) ?? true, [])
  const onState = useCallback((p: string, s: SaveState) => setSaveStates((all) => ({ ...all, [p]: s })), [])
  const registerFlush = useCallback((f: (() => Promise<boolean>) | null) => { flushRef.current = f }, [])
  return { kept, savedTick, onState, flushRef, flushCurrent, registerFlush }
}
