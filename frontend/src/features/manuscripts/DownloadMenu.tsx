import { ChevronDown, Download } from 'lucide-react'
import { api, type ManuscriptDetail } from '@/api/client'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'

type Props = { manuscript: Pick<ManuscriptDetail, 'id' | 'title' | 'has_pdf' | 'compiled_at'> }

/** The paper's files to take away: the compiled PDF, the LaTeX source alone, or both in one zip. */
export function DownloadMenu({ manuscript: m }: Props) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm"><Download aria-hidden />Download<ChevronDown aria-hidden /></Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {m.has_pdf ? (
          <DropdownMenuItem asChild>
            <a href={api.manuscriptPdfUrl(m.id, m.compiled_at)} download={`${m.title}.pdf`}>PDF</a>
          </DropdownMenuItem>
        ) : (
          <DropdownMenuItem disabled>PDF — compile first</DropdownMenuItem>
        )}
        <DropdownMenuItem asChild>
          <a href={api.manuscriptExportUrl(m.id, { pdf: false })} download>LaTeX source (.zip)</a>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <a href={api.manuscriptExportUrl(m.id)} download>Source and PDF (.zip)</a>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
