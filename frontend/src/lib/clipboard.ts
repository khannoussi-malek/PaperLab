/** Copies `text`, or rejects with a sentence to show the reader. Shared by the reader's menus and Connect Claude. */
export async function copyText(text: string): Promise<void> {
  if (!navigator.clipboard) throw new Error('Copying needs clipboard access, which this browser blocks here.')
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    throw new Error('Could not copy: the browser blocked clipboard access.')
  }
}
