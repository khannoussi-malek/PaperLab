import { useEffect, useRef, useState } from 'react'
import type { ImportResult } from '@/api/client'
import { Button } from '@/components/ui/button'
import { copyText } from '@/lib/clipboard'

export const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`
const doiUrl = (doi: string) => `https://doi.org/${doi}`

/** One line per entry, for pasting into a to-do list or a message to a librarian. */
const listText = (entries: ImportResult['needs_pdf']) =>
  entries.map((e) => (e.doi ? `${e.title} - ${doiUrl(e.doi)}` : e.title)).join('\n')

/** What an import did, in words, then the entries that still need the reader. */
export function ImportResultView({ result }: { result: ImportResult }) {
  const [copied, setCopied] = useState<string | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => heading.current?.focus(), [])
  const { needs_pdf: needsPdf, failed } = result

  async function copy() {
    try {
      await copyText(listText(needsPdf))
      setCopied('Copied')
    } catch (e) {
      setCopied((e as Error).message)
    }
  }

  const already = result.already_in_library
  return (
    <div aria-live="polite" className="flex flex-col gap-3 text-sm">
      <h3 ref={heading} tabIndex={-1} className="font-medium outline-none">
        Import finished
      </h3>
      <p>
        Imported {plural(result.imported, 'new paper')}. {already} {already === 1 ? 'was' : 'were'} already in your
        library, {plural(result.pdfs_attached, 'PDF')} attached, {plural(result.notes, 'note')}.
      </p>
      {result.stopped && (
        <p>
          {result.stopped}
          {result.not_reached.length > 0 && ` ${plural(result.not_reached.length, 'entry')} not reached.`}
        </p>
      )}
      {needsPdf.length > 0 && (
        <details open>
          <summary className="cursor-pointer font-medium">Needs a PDF ({needsPdf.length})</summary>
          <p className="py-1 text-muted-foreground">
            No free copy was found. Add these by hand when you have the PDF.
          </p>
          <ul className="max-h-40 list-disc overflow-auto pl-5">
            {needsPdf.map((e, i) => (
              <li key={`${e.title}-${i}`}>
                {e.title}
                {e.doi && (
                  <>
                    {' '}
                    <a className="underline" href={doiUrl(e.doi)} target="_blank" rel="noreferrer">
                      {e.doi}
                    </a>
                  </>
                )}
              </li>
            ))}
          </ul>
          <Button className="mt-2" variant="outline" size="sm" onClick={copy}>
            Copy list
          </Button>
          {copied && <span className="ml-2 text-muted-foreground">{copied}</span>}
        </details>
      )}
      {failed.length > 0 && (
        <details open>
          <summary className="cursor-pointer font-medium">Couldn't import ({failed.length})</summary>
          <ul className="max-h-40 list-disc overflow-auto pl-5">
            {failed.map((f, i) => (
              <li key={`${f.title}-${i}`}>
                {f.title}: {f.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}
