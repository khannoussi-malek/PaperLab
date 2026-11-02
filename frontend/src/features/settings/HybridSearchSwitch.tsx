import { Alert, AlertDescription } from '@/components/ui/alert'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { useSetHybridSearch } from '@/api/queries'

/** Settings → Search: also rank chunks by the question's exact words when a search covers several papers. */
export function HybridSearchSwitch({ enabled }: { enabled: boolean }) {
  const update = useSetHybridSearch()
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2.5">
        <Checkbox
          id="hybrid-search"
          checked={enabled}
          disabled={update.isPending}
          aria-describedby="hybrid-search-help"
          onCheckedChange={(checked) => update.mutate(checked === true)}
        />
        <Label htmlFor="hybrid-search">Also match exact words when searching across papers</Label>
      </div>
      <p id="hybrid-search-help" className="pl-6.5 text-xs text-muted-foreground">
        Finds rare names and numbers, like a drug name, that search by meaning can miss. Search inside a single paper stays as it is. A broad question can take a couple of seconds longer.
      </p>
      {update.error && (
        <Alert variant="destructive" className="border-glass-border">
          <AlertDescription>{update.error.message}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}
