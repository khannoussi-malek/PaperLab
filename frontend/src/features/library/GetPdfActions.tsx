import { useRef, useState } from 'react'
import { AlreadyInLibraryError, NoFreePdfError } from '@/api/client'
import { useFindPaperPdf, useUploadPaperPdf } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { codeInWords, outcomeInWords } from '@/lib/errorWords'
import { readerHref } from '@/lib/route'

/** A visually hidden native PDF input (kept labelled, so it stays reachable by label) driven by a visible button. */
export function UploadPdfButton({
  title,
  disabled,
  onPick,
}: {
  title: string
  disabled: boolean
  onPick: (file: File, onFail: () => void) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  const [fileName, setFileName] = useState<string | null>(null)
  return (
    <>
      <input
        ref={input}
        type="file"
        accept="application/pdf"
        aria-label={`Upload PDF for ${title}`}
        className="sr-only"
        tabIndex={-1}
        disabled={disabled}
        onChange={(e) => {
          const file = e.target.files?.[0]
          e.target.value = '' // so picking the same file again (after a refusal) fires change
          if (!file) return
          setFileName(file.name)
          onPick(file, () => setFileName(null))
        }}
      />
      <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={() => input.current?.click()}>
        <span>
          {fileName ?? 'Upload PDF'} <span className="sr-only">for {title}</span>
        </span>
      </Button>
    </>
  )
}

const isWebUrl = (url: string) => /^https?:\/\//i.test(url)

/** What a refused find says: what was tried and where a copy may be, the library's own copy, or the refusal in words. */
function FindFailure({ error }: { error: Error }) {
  if (error instanceof AlreadyInLibraryError) {
    return (
      <p>
        Your library already holds this work as another paper.{' '}
        <a href={readerHref(error.paperId)} className="text-primary hover:underline">
          Open it
        </a>
      </p>
    )
  }
  if (!(error instanceof NoFreePdfError)) return <p>{codeInWords(error.message)}</p>
  const copies = error.freeCopies.filter(isWebUrl)
  return (
    <div className="flex flex-col gap-1">
      <p>No free copy was found.</p>
      {error.tried.length > 0 && (
        <ul className="list-disc pl-4">
          {error.tried.map((t, i) => (
            <li key={i} className="wrap-anywhere">
              {t.url}: {outcomeInWords(t.outcome)}
            </li>
          ))}
        </ul>
      )}
      {copies.length > 0 && (
        <>
          <p>Where a copy may be:</p>
          <ul className="list-disc pl-4">
            {copies.map((url) => (
              <li key={url} className="wrap-anywhere">
                <a href={url} target="_blank" rel="noreferrer" className="text-primary hover:underline">
                  {url}
                </a>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

/** "Find free copy" for a paper saved without a PDF, with its result: looking, found (the list refreshes), or why not. */
export function FindFreeCopy({ paperId, title }: { paperId: string; title: string }) {
  const find = useFindPaperPdf(paperId)
  return (
    <>
      <Button type="button" variant="outline" size="sm" disabled={find.isPending} onClick={() => find.mutate()}>
        <span>
          Find free copy <span className="sr-only">for {title}</span>
        </span>
      </Button>
      {find.isPending && <p role="status" className="basis-full text-xs text-muted-foreground">Looking for a free copy…</p>}
      {find.isError && (
        <div role="alert" className="basis-full text-xs text-muted-foreground">
          <FindFailure error={find.error} />
        </div>
      )}
    </>
  )
}

/** The two ways to get a paper saved without a PDF its PDF: pick one, or have PaperLab look for a free copy. */
export function GetPdfActions({ paperId, title }: { paperId: string; title: string }) {
  const upload = useUploadPaperPdf(paperId)
  return (
    <div className="flex flex-wrap items-center gap-2">
      <UploadPdfButton
        title={title}
        disabled={upload.isPending}
        onPick={(file, onFail) => upload.mutate(file, { onError: onFail })}
      />
      <FindFreeCopy paperId={paperId} title={title} />
      {upload.isError && (
        <p role="alert" className="basis-full text-xs text-destructive">
          {codeInWords(upload.error.message)}
        </p>
      )}
    </div>
  )
}
