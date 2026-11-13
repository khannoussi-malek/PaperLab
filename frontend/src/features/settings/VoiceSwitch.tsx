import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { keys } from '@/api/queries'
import type { VoiceStatus } from '@/api/client'
import { delayedIn } from '@/components/motion'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import type { VoiceBridge } from './desktop'

const OUT_OF_MEMORY = 'Docker ran out of memory for voice. Give Docker more memory in its settings, then turn voice off and on.'

/** The "Ask questions out loud" switch, the only part of Voice that needs the desktop app. It turns the voice program
 * on or off, shows the latest progress line while it turns on, and says why when Docker killed the program for memory. */
export function VoiceSwitch({ voice, stage }: { voice: VoiceBridge; stage: VoiceStatus['stage'] | undefined }) {
  const queryClient = useQueryClient()
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [busy, setBusy] = useState(false)
  const [line, setLine] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [outOfMemory, setOutOfMemory] = useState(false)
  // The last value asked for, so a late answer to an earlier request never overwrites a newer one.
  const wanted = useRef<boolean | null>(null)

  useEffect(() => {
    let current = true
    voice.getVoiceEnabled().then(
      (value) => current && setEnabled(value),
      (reason: unknown) => {
        console.warn('reading voice on or off failed', reason)
        if (!current) return
        setEnabled(false)
        setError("The desktop app didn't answer. Restart it to change this.")
      },
    )
    voice.voiceOutOfMemory().then(
      (value) => current && setOutOfMemory(value),
      () => undefined,
    )
    return () => {
      current = false
    }
  }, [voice])

  useEffect(() => voice.onVoiceProgress(setLine), [voice])

  function refreshStatus() {
    void queryClient.invalidateQueries({ queryKey: keys.voiceStatus })
  }

  async function change(value: boolean) {
    wanted.current = value
    setEnabled(value)
    setBusy(true)
    setError(null)
    setLine(null)
    try {
      const result = await voice.setVoiceEnabled(value)
      if (result.ok) {
        refreshStatus()
      } else {
        if (wanted.current === value) setEnabled(!value)
        setError(result.detail ?? "Voice didn't turn on. Try again.")
      }
    } catch (reason: unknown) {
      console.warn('turning voice on or off failed', reason)
      if (wanted.current === value) setEnabled(!value)
      setError("Voice didn't turn on. Try again.")
    } finally {
      setBusy(false)
      setLine(null)
      voice.voiceOutOfMemory().then(setOutOfMemory, () => undefined)
    }
  }

  async function removeModels() {
    setBusy(true)
    setError(null)
    try {
      const result = await voice.removeVoiceModels()
      if (result.ok) refreshStatus()
      else setError(result.detail ?? "The voice models didn't come off. Try again.")
    } catch (reason: unknown) {
      console.warn('removing voice models failed', reason)
      setError("The voice models didn't come off. Try again.")
    } finally {
      setBusy(false)
    }
  }

  const showOutOfMemory = outOfMemory && (stage === 'off' || stage === 'failed')

  return (
    <div className="flex items-start justify-between gap-4">
      <div className="grid gap-1">
        <Label htmlFor="ask-out-loud">Ask questions out loud</Label>
        <p id="ask-out-loud-help" className="text-sm text-muted-foreground">
          Turns your speech into text and reads answers aloud, all on this computer. The first time downloads about 600 MB.
        </p>
        {busy && line && (
          <p role="status" className="text-sm text-muted-foreground">
            {line}
          </p>
        )}
        {showOutOfMemory && (
          <Alert variant="destructive" className="border-glass-border">
            <AlertDescription>{OUT_OF_MEMORY}</AlertDescription>
          </Alert>
        )}
        {error && (
          <Alert variant="destructive" className="border-glass-border">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {enabled === false && (
          <Button type="button" variant="outline" size="sm" className="w-fit" disabled={busy} onClick={() => void removeModels()}>
            Remove voice models
          </Button>
        )}
      </div>
      {enabled === null ? (
        <p className={cn('text-sm text-muted-foreground', delayedIn)}>Loading…</p>
      ) : (
        <Switch id="ask-out-loud" aria-describedby="ask-out-loud-help" checked={enabled} onCheckedChange={(value) => void change(value)} />
      )}
    </div>
  )
}
