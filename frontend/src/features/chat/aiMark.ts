/** The AI mark's words: the model that wrote an answer, its connection when known, and the prompt version. */
export function aiMark(model: string, connectionName: string | null, promptVersion: number): string {
  return connectionName ? `AI · ${model} · ${connectionName} · prompt v${promptVersion}` : `AI · ${model} · prompt v${promptVersion}`
}
