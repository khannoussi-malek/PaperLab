import type { APIRoute } from 'astro'
import { AUDIENCES } from '../lib/audiences'
import { FEATURES } from '../lib/features'
import { TERMS } from '../lib/glossary'
import { GUIDES } from '../lib/guides'
import { BASE, REPO, SITE } from '../lib/site'

// llms.txt (llmstxt.org): a plain summary with links, for AI assistants and crawlers. Built from the same lists as
// the pages, so a new guide or feature is listed without editing this file.
const url = (path: string) => `${SITE}${BASE}${path}`
const line = (title: string, path: string, note: string) => `- [${title}](${url(path)}): ${note}`

export const GET: APIRoute = () => {
  const body = [
    '# PaperLab',
    '',
    '> PaperLab is a free, open-source, local-first reader for research papers. Highlights become notes anchored to the exact passage they came from, and AI answers cite the passages they used so each claim can be checked against the page. AI text is always stored apart from yours and labelled. It runs on macOS, Windows and Linux, works with local models through Ollama, and never gets past a paywall.',
    '',
    '## Pages',
    '',
    line('Home', '', 'what PaperLab is and who builds it'),
    line('Download', 'download/', 'desktop app for macOS, Windows and Linux (needs Docker)'),
    line('Systematic reviews', 'systematic-reviews/', 'search, screening, snowballing and PRISMA counts'),
    line('FAQ', 'faq/', 'privacy, models, paywalls, Docker'),
    line('About', 'about/', 'who builds PaperLab and why'),
    '',
    '## Who it is for',
    '',
    ...AUDIENCES.map((a) => line(a.name, `for/${a.slug}/`, a.blurb)),
    '',
    '## Features',
    '',
    ...FEATURES.map((f) => line(f.name, `features/${f.slug}/`, f.tagline + (f.next ? ' (next release)' : ''))),
    '',
    '## Guides',
    '',
    ...GUIDES.map((g) => line(g.title, g.path, g.blurb)),
    '',
    '## Glossary',
    '',
    ...TERMS.map((t) => line(t.name, `glossary/${t.slug}/`, t.description)),
    '',
    '## Project',
    '',
    `- [Source code](${REPO}): Apache-2.0; FastAPI, Postgres with pgvector, React, PDF.js, an MCP server`,
    '',
  ].join('\n')
  return new Response(body, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } })
}
