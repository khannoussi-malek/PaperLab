import type { ReactNode } from 'react'
import { useClearMcpActivity, useMcpActivity, useMcpSettings, useSetMcpWrites } from '@/api/queries'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ErrorAlert } from '@/features/library/ErrorAlert'

const WHEN = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium' })
const HELP_ID = 'mcp-writes-help'

// Copied from ConnectClaudePage.tsx, which can't be imported here without a cycle.
function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3">
      <h2 id={id} className="font-heading text-xl font-semibold">
        {title}
      </h2>
      {children}
    </section>
  )
}

/** Connect Claude's activity: the tool calls MCP clients made, and the owner's switch for changes from Claude. */
export function ClaudeActivity() {
  const activity = useMcpActivity()
  const settings = useMcpSettings()
  const setWrites = useSetMcpWrites()
  const clear = useClearMcpActivity()
  const rows = activity.data ?? []

  return (
    <Section id="activity-heading" title="What Claude did">
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-4">
          <Label htmlFor="mcp-writes">Let Claude change your library</Label>
          <Switch
            id="mcp-writes"
            checked={settings.data?.writes_enabled ?? true}
            disabled={!settings.data || setWrites.isPending}
            aria-describedby={HELP_ID}
            onCheckedChange={(on) => setWrites.mutate(on)}
          />
        </div>
        <p id={HELP_ID} className="text-sm text-muted-foreground">
          Off: Claude can still search and read, but can't add, tag, write or delete anything.
        </p>
        {settings.isError && <ErrorAlert message={settings.error.message} />}
        {setWrites.error && <ErrorAlert message={setWrites.error.message} />}
      </div>

      {activity.isError && <ErrorAlert message={activity.error.message} />}
      {activity.data && rows.length === 0 && <p className="text-sm">No tool calls yet.</p>}
      {rows.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>When</TableHead>
              <TableHead>Tool</TableHead>
              <TableHead>Asked with</TableHead>
              <TableHead>Result</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, index) => (
              <TableRow key={`${row.at}-${index}`}>
                <TableCell className="whitespace-nowrap">{WHEN.format(new Date(row.at))}</TableCell>
                <TableCell>
                  <span className="font-mono text-xs">{row.tool}</span>
                  {row.is_write && (
                    <Badge variant="secondary" className="ml-2">
                      Change
                    </Badge>
                  )}
                </TableCell>
                <TableCell>
                  <code className="font-mono text-xs break-all">{row.arguments}</code>
                </TableCell>
                <TableCell>{row.outcome}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {clear.error && <ErrorAlert message={clear.error.message} />}
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant="outline" className="self-start" disabled={rows.length === 0 || clear.isPending}>
            Clear the list
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Clear the list?</AlertDialogTitle>
            <AlertDialogDescription>The tool calls listed here are removed. Your library doesn't change.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => clear.mutate()}>Clear</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Section>
  )
}
