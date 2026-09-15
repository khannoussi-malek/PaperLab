/** One `progress` event of an Ollama pull. */
export type PullLine = { status: string; total: number | null; completed: number | null }

/** The line in words, with a whole percentage while Ollama reports sizes (null while it only reports a status). */
export function describePull(line: PullLine): { label: string; percent: number | null } {
  if (!line.total || line.completed === null) return { label: line.status, percent: null }
  const percent = Math.min(100, Math.floor((line.completed / line.total) * 100))
  return { label: `${line.status} · ${percent}%`, percent }
}
