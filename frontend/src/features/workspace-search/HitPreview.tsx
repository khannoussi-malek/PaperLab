import type { Hit } from '@/api/client'
import { glass } from '@/components/glass'
import { cn } from '@/lib/utils'

/** The hovered or focused hit's title, byline and abstract — same split as the library's PaperList/PaperPreview:
 * PaperMenu/PaperContextMenu (HitMenu here) stay pure action menus, and this is the dedicated read surface. A
 * hit whose candidate never matched an ExternalRef (title/authors/year/venue/abstract all null) falls back to
 * the normalized_title every hit always has, and shows nothing else. */
export function HitPreview({ hit }: { hit: Hit }) {
  const byline = [hit.authors?.join(', '), hit.year, hit.venue].filter(Boolean).join(' · ')

  return (
    <aside
      aria-label="Hit preview"
      className={cn('hit-preview flex flex-col gap-2 overflow-y-auto rounded-xl p-4 ring-1 ring-glass-border', glass)}
    >
      <h2 className="font-heading text-lg leading-snug font-semibold wrap-anywhere">{hit.title ?? hit.normalized_title}</h2>
      {byline && <p className="text-sm text-muted-foreground">{byline}</p>}
      {hit.doi && (
        <a
          href={`https://doi.org/${encodeURIComponent(hit.doi)}`}
          target="_blank"
          rel="noreferrer"
          className="w-fit text-xs text-primary hover:underline"
        >
          doi:{hit.doi}
        </a>
      )}
      {hit.abstract ? (
        <p className="mt-2 text-sm whitespace-pre-line">{hit.abstract}</p>
      ) : (
        <p className="mt-2 text-sm text-muted-foreground">No abstract available for this hit.</p>
      )}
    </aside>
  )
}
