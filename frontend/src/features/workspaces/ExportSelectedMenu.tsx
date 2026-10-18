import { useMutation } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'

function save(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = Object.assign(document.createElement('a'), { href: url, download: filename })
  link.click()
  URL.revokeObjectURL(url)
}

/** "Export selected…" on the Papers selection bar: the chosen papers as a BibTeX or RIS download. */
export function ExportSelectedMenu({ paperIds }: { paperIds: string[] }) {
  const exportIt = useMutation({
    mutationFn: async (format: 'bibtex' | 'ris') => {
      const { blob, filename } = await api.exportSelection(paperIds, format)
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
          Couldn't export those papers: {exportIt.error.message}
        </span>
      )}
    </>
  )
}
