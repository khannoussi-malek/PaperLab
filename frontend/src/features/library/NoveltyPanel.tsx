import { useId, useState } from 'react'
import { useNovelty } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { codeInWords } from '@/lib/errorWords'
import { readerHref } from '@/lib/route'
import { ErrorAlert } from './ErrorAlert'

const MAX_CHARS = 6000

/** Where a hit's passage sits: its page, or "abstract" when the match came from the abstract. */
const where = (page: number | null, fromAbstract: boolean) => (fromAbstract ? 'abstract' : page === null ? null : `p. ${page}`)

/** Asks whether an idea or abstract is already in the library. Mounted only while open, so it keeps no state between openings. */
export function NoveltyPanel() {
  const [text, setText] = useState('')
  const novelty = useNovelty()
  const helpId = useId()
  const result = novelty.data

  return (
    <section aria-labelledby={`${helpId}-title`} className="flex flex-col gap-3">
      <h2 id={`${helpId}-title`} className="text-base font-medium">Has this been done?</h2>
      <div className="flex flex-col gap-2">
        <Label htmlFor={`${helpId}-idea`}>Paste an idea or an abstract</Label>
        <p className="text-sm text-muted-foreground">Searches your own library only.</p>
        <Textarea
          id={`${helpId}-idea`}
          value={text}
          maxLength={MAX_CHARS}
          aria-describedby={`${helpId}-count`}
          onChange={(e) => {
            setText(e.target.value)
            novelty.reset()
          }}
        />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span id={`${helpId}-count`} className="text-sm text-muted-foreground">{text.length} / {MAX_CHARS} characters</span>
          <Button disabled={text.trim() === '' || novelty.isPending} onClick={() => novelty.mutate(text.trim())}>Check</Button>
        </div>
      </div>

      {novelty.error && <ErrorAlert message={codeInWords(novelty.error.message)} />}

      {result && (
        <div className="flex flex-col gap-3">
          {result.papers.length === 0 ? (
            <p>Nothing close in your library</p>
          ) : (
            <ul className="flex flex-col gap-3">
              {result.papers.map((p) => {
                const location = where(p.page, p.from_abstract)
                return (
                  <li key={p.chunk_id} className="flex flex-col gap-1 rounded-lg border border-glass-border p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <a href={readerHref(p.paper_id)} className="font-medium underline-offset-4 hover:underline">{p.title}</a>
                      <Badge variant="secondary">{p.label}</Badge>
                    </div>
                    {location && <p className="text-sm text-muted-foreground">{location}</p>}
                    <blockquote className="line-clamp-3 border-l-2 border-border pl-3 text-sm">{p.passage}</blockquote>
                  </li>
                )
              })}
            </ul>
          )}
          <p className="text-sm text-muted-foreground">{result.note}</p>
        </div>
      )}
    </section>
  )
}
