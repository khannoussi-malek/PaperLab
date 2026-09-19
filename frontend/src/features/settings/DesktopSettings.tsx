import { useEffect, useState } from 'react'
import { delayedIn } from '@/components/motion'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { useDesktop, type PaperlabDesktop } from './desktop'

/** Settings → Desktop app (P5, P8): only inside the desktop app, where window.paperlabDesktop exists. */
export function DesktopSettings() {
  const desktop = useDesktop()
  return desktop === null ? null : <DesktopSection desktop={desktop} />
}

type Toggle = {
  id: string
  label: string
  help: string
  read: () => Promise<boolean>
  write: (value: boolean) => Promise<void>
}

function DesktopSection({ desktop }: { desktop: PaperlabDesktop }) {
  const toggles: Toggle[] = [
    {
      id: 'keep-running',
      label: 'Keep PaperLab running when the window is closed',
      help: 'Claude Desktop can use your library and uploads keep processing while it runs.',
      read: desktop.getKeepRunning,
      write: desktop.setKeepRunning,
    },
    {
      id: 'check-updates',
      label: 'Check for updates on launch',
      help: 'Each time it opens, PaperLab asks GitHub whether a newer version is out.',
      read: desktop.getUpdatesEnabled,
      write: desktop.setUpdatesEnabled,
    },
  ]
  return (
    <section aria-labelledby="desktop-app-heading" className="flex flex-col gap-4">
      <h2 id="desktop-app-heading" className="font-heading text-xl font-semibold">
        Desktop app
      </h2>
      {toggles.map((toggle) => (
        <DesktopSwitch key={toggle.id} {...toggle} />
      ))}
    </section>
  )
}

/** One setting: its label and line, and a switch that shows only once the app has answered — "Loading…" until then,
 * so it never flashes the wrong position while the read is in flight. */
function DesktopSwitch({ id, label, help, read, write }: Toggle) {
  const [checked, setChecked] = useState<boolean | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    read().then(setChecked, (reason: unknown) => {
      console.warn('reading a desktop setting failed', reason)
      setError("The desktop app didn't answer. Restart it to change this.")
    })
  }, [read])

  function change(value: boolean) {
    setChecked(value)
    setError(null)
    write(value).catch((reason: unknown) => {
      console.warn('saving a desktop setting failed', reason)
      setChecked(!value)
      setError("The desktop app didn't save this. Try again.")
    })
  }

  return (
    <div className="flex items-start justify-between gap-4">
      <div className="grid gap-1">
        <Label htmlFor={id}>{label}</Label>
        <p className="text-sm text-muted-foreground">{help}</p>
        {error && (
          <Alert variant="destructive" className="border-glass-border">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
      </div>
      {checked === null ? (
        <p className={cn('text-sm text-muted-foreground', delayedIn)}>Loading…</p>
      ) : (
        <Switch id={id} checked={checked} onCheckedChange={change} />
      )}
    </div>
  )
}
