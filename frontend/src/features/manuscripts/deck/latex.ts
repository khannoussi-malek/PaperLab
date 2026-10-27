const SPECIALS: Record<string, string> = {
  '\\': '\\textbackslash{}',
  '~': '\\textasciitilde{}',
  '^': '\\textasciicircum{}',
}

/** Text that LaTeX prints as written: every special character escaped in one pass. */
export const latexEscape = (text: string): string =>
  text.replace(/[\\#$%&_{}~^]/g, (c) => SPECIALS[c] ?? `\\${c}`)
