import { useGlass } from '@/components/liquid-glass/useGlass'
import { blurPx, GLASS_AREAS, GLASS_RANGES, type GlassArea, type GlassSettings as Settings } from '@/components/liquid-glass/settings'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { GlassPreview } from './GlassPreview'

const DEMO_URL = 'https://liquid-glass.maxrovensky.com'

type SliderKey = keyof typeof GLASS_RANGES

/** The sliders, in the demo's order and under its names; the last two are PaperLab's own. */
const SLIDERS: { key: SliderKey; label: string; help: string; show: (settings: Settings) => string }[] = [
  { key: 'displacementScale', label: 'Displacement scale', help: 'How far the edge bends what is behind it. 0 is flat glass.', show: (s) => String(s.displacementScale) },
  { key: 'blurAmount', label: 'Blur amount', help: 'How frosted the glass is: 4 px, plus 32 px per whole step.', show: (s) => `${s.blurAmount} (${blurPx(s)} px)` },
  { key: 'saturation', label: 'Saturation', help: 'How rich the colours behind the glass look.', show: (s) => `${s.saturation}%` },
  { key: 'aberrationIntensity', label: 'Chromatic aberration', help: 'How far red, green and blue split at the edge.', show: (s) => s.aberrationIntensity.toFixed(1) },
  { key: 'edgeWidth', label: 'Edge width', help: 'How deep from the edge the light bends.', show: (s) => `${s.edgeWidth} px` },
  { key: 'opacity', label: 'Opacity', help: 'How much tint the glass carries. Clearer glass shows more bending, but text over busy content gets harder to read.', show: (s) => `${Math.round(s.opacity * 100)}%` },
]

const AREA_LABELS: Record<GlassArea, string> = {
  floating: 'Menus, popovers and dialogs',
  chrome: 'Toolbar and side rail',
  buttons: 'Buttons and the workspace tab pill',
  reader: 'Reader toolbar and side panel',
}

/** Settings → Glass: tune the liquid glass live (see "Glass" in design-system/MASTER.md). */
export function GlassSettings() {
  const { settings, update, reset, bendsLight } = useGlass()
  return (
    <section aria-labelledby="glass-heading" className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h2 id="glass-heading" className="font-heading text-xl font-semibold">
          Glass
        </h2>
        <p className="text-sm text-muted-foreground">
          Liquid glass bends and frosts what is behind menus, dialogs, the toolbar and side rail, buttons and the
          reader's panels. Changes apply at once and are remembered in this browser.
        </p>
        <p className="text-sm text-muted-foreground">
          To find values you like, try the{' '}
          <a href={DEMO_URL} target="_blank" rel="noreferrer" className="text-primary underline underline-offset-2">
            liquid-glass-react demo
          </a>{' '}
          in Chrome: its first four sliders are the same as these and mean the same.
        </p>
      </div>

      <GlassPreview />

      {!bendsLight && (
        <Alert>
          <AlertDescription>
            This browser can't bend light, so the glass stays frosted here. Chrome, Edge, Arc and the PaperLab desktop
            app show the full effect.
          </AlertDescription>
        </Alert>
      )}

      <div className="flex items-center gap-2.5">
        <Switch id="glass-enabled" checked={settings.enabled} onCheckedChange={(enabled) => update({ enabled })} />
        <Label htmlFor="glass-enabled">Liquid glass</Label>
      </div>

      <fieldset disabled={!settings.enabled} className="flex flex-col gap-5 disabled:opacity-50">
        <legend className="sr-only">Glass settings</legend>
        {SLIDERS.map(({ key, label, help, show }) => {
          const { min, max, step } = GLASS_RANGES[key]
          return (
            <div key={key} className="flex flex-col gap-1.5">
              <div className="flex items-baseline justify-between gap-4">
                <Label htmlFor={`glass-${key}`}>{label}</Label>
                <output htmlFor={`glass-${key}`} className="text-sm tabular-nums text-muted-foreground">
                  {show(settings)}
                </output>
              </div>
              <input
                id={`glass-${key}`}
                type="range"
                min={min}
                max={max}
                step={step}
                value={settings[key]}
                aria-describedby={`glass-${key}-help`}
                onChange={(event) => update({ [key]: Number(event.target.value) })}
                className="w-full accent-primary"
              />
              <p id={`glass-${key}-help`} className="text-xs text-muted-foreground">
                {help}
              </p>
            </div>
          )
        })}

        <div className="flex flex-col gap-2.5">
          <span className="text-sm font-medium">Where</span>
          {GLASS_AREAS.map((area) => (
            <div key={area} className="flex items-center gap-2.5">
              <Checkbox
                id={`glass-area-${area}`}
                checked={settings.areas[area]}
                onCheckedChange={(checked) => update({ areas: { ...settings.areas, [area]: checked === true } })}
              />
              <Label htmlFor={`glass-area-${area}`}>{AREA_LABELS[area]}</Label>
            </div>
          ))}
        </div>
      </fieldset>

      <div>
        <Button variant="outline" onClick={reset}>
          Reset to defaults
        </Button>
      </div>
    </section>
  )
}
