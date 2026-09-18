import { useMemo } from 'react'
import { FADED, nodeColor } from './graphModel'
import { DIAGONAL, matrix, MATRIX_CAP_LINE, MATRIX_CAPTION } from './matrixModel'
import type { ViewProps } from './viewModel'

/**
 * The one view a screen reader can read cell by cell (D114): a real table with a caption, row headers that focus a
 * paper (each wearing its node's colour), and a name on every linked cell. It scrolls inside the middle column with
 * the header row and the first column stuck in place. A plain <table>: the shadcn Table's own overflow box would
 * break `sticky` here.
 */
export function MatrixView({ nodes, links, theme, colors, inFocus, onSelect }: ViewProps) {
  const { papers, cells, capped } = useMemo(() => matrix(nodes, links, theme), [nodes, links, theme])
  const fade = (...ids: string[]) =>
    inFocus !== null && ids.some((id) => !inFocus.has(id)) ? { opacity: FADED } : undefined

  return (
    <div data-view="matrix" className="flex min-h-0 flex-1 flex-col gap-2 p-3">
      {capped && <p className="text-sm text-muted-foreground">{MATRIX_CAP_LINE}</p>}
      <div className="min-h-0 flex-1 overflow-auto rounded-md">
        <table className="border-separate border-spacing-0 text-sm">
          <caption className="sr-only">{MATRIX_CAPTION}</caption>
          <thead>
            <tr>
              <td className="sticky top-0 left-0 z-20 bg-background" />
              {papers.map((paper) => (
                <th
                  key={paper.id}
                  scope="col"
                  title={paper.title}
                  className="sticky top-0 z-10 bg-background px-0.5 pb-1 align-bottom font-normal text-muted-foreground"
                  style={fade(paper.id)}
                >
                  <span className="block max-h-40 rotate-180 truncate [writing-mode:vertical-rl]">{paper.title}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {papers.map((row, r) => (
              <tr key={row.id}>
                <th scope="row" className="sticky left-0 z-10 bg-background p-0 text-left font-normal">
                  <button
                    type="button"
                    title={row.title}
                    className="flex w-48 items-center gap-2 rounded-md px-2 py-1 text-left transition-colors duration-150 outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
                    onClick={() => onSelect(row.id)}
                  >
                    <span
                      aria-hidden
                      className="size-2 shrink-0 rounded-full"
                      style={{ backgroundColor: nodeColor(row, colors, theme), ...fade(row.id) }}
                    />
                    <span className="min-w-0 truncate" style={fade(row.id)}>
                      {row.title}
                    </span>
                  </button>
                </th>
                {cells[r].map((cell, c) => (
                  <td
                    key={papers[c].id}
                    title={cell?.name}
                    className="size-6 border border-glass-border text-center text-muted-foreground"
                    style={{ backgroundColor: cell?.color, ...fade(row.id, papers[c].id) }}
                  >
                    {r === c ? DIAGONAL : cell && <span className="sr-only">{cell.name}</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
