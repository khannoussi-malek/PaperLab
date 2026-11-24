import { useMemo } from 'react'
import type { useManuscript } from '@/services/queries'
import { parseCompileErrors } from '@/features/manuscripts/compileErrors'
import { FileList } from '@/features/manuscripts/FileList'
import { BlueprintPanel } from '@/features/manuscripts/BlueprintPanel'
import { FinalStepsChecklist } from '@/features/manuscripts/FinalStepsChecklist'
import { GuidelineChecklist } from '@/features/manuscripts/GuidelineChecklist'
import { SectionList } from '@/features/manuscripts/SectionList'
import type { SectionRow } from '@/features/manuscripts/sections'
import type { outline } from '@/features/manuscripts/outline'
import type { useStudioCommands } from '@/features/manuscripts/useStudioCommands'

/** The Sections column: the outline and section list, the file list, the blueprint and the checklists of a manuscript. */
export function SectionsColumn({ manuscriptId, data, path, cursorLine, fileTexts, items, sectionAsk, flushCurrent, jumpTo, openSection }: {
  manuscriptId: string
  data: NonNullable<ReturnType<typeof useManuscript>['data']>
  path: string
  cursorLine: number
  fileTexts: Record<string, string>
  items: ReturnType<typeof outline>
  sectionAsk: ReturnType<typeof useStudioCommands>['sectionAsk']
  flushCurrent: () => Promise<boolean>
  jumpTo: (f: string, line: number) => void
  openSection: (row: SectionRow) => void
}) {
  const errorsByFile = useMemo(
    () => parseCompileErrors(data.compile_errors).reduce<Record<string, number>>((n, e) => (e.file ? { ...n, [e.file]: (n[e.file] ?? 0) + 1 } : n), {}),
    [data.compile_errors],
  )
  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-auto py-2">
      <SectionList
        manuscriptId={manuscriptId}
        main={data.main_file}
        texts={fileTexts}
        filePaths={data.files.map((f) => f.path)}
        errorsByFile={errorsByFile}
        current={{ path, line: cursorLine }}
        items={items}
        flushCurrent={flushCurrent}
        onOpen={openSection}
        onJump={jumpTo}
        request={sectionAsk}
      />
      <details className="px-0">
        <summary className="cursor-pointer px-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">All files</summary>
        <FileList manuscriptId={manuscriptId} files={data.files} current={path} main={data.main_file} flushCurrent={flushCurrent} />
      </details>
      <BlueprintPanel manuscriptId={manuscriptId} files={data.files} mainFile={data.main_file} title={data.title} template={data.template} />
      <FinalStepsChecklist manuscriptId={manuscriptId} checklist={data.checklist} />
      <GuidelineChecklist manuscriptId={manuscriptId} checklist={data.checklist} />
    </div>
  )
}
