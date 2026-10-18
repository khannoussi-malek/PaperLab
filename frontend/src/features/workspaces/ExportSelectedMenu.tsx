import { useMutation } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'

function save(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = Object.assign(document.createElement('a'), { href: url, download: filename })
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 0) // after the click has started the download
}

/** The API's snake_case refusal codes, in words. */
function plainError(error: Error): string {
  if (error.message === 'no_papers') return 'Pick at least one paper to export.'
  if (error.message === 'too_many_papers') return 'You can export up to 1000 papers at a time.'
  return "Couldn't build the reference list. Try again."
}

/** "Export selected…" on a selection bar: the chosen papers as a BibTeX or RIS download. From a workspace, its
 * keywords come along; from the library there is none. */
export function ExportSelectedMenu({ workspaceId, paperIds }: { workspaceId?: string; paperIds: string[] }) {
  const exportIt = useMutation({
    mutationFn: async (format: 'bibtex' | 'ris') => {
      const { blob, filename } = await api.exportSelection(paperIds, format, workspaceId)
      save(blob, filename)
    },
  })
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" disabled={exportIt.isPending}>
            Export selected…
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onSelect={() => exportIt.mutate('bibtex')}>BibTeX</DropdownMenuItem>
          <DropdownMenuItem onSelect={() => exportIt.mutate('ris')}>RIS</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {exportIt.error && (
        <span role="alert" className="text-sm text-destructive">
          {plainError(exportIt.error)}
        </span>
      )}
    </>
  )
}
