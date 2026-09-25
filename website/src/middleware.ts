import { defineMiddleware } from 'astro:middleware'

// Runs as each page is built: every link to another site opens in a new tab, without handing it window.opener.
// One rule here, so a link added later can't forget it.
const EXTERNAL = /<a\b(?![^>]*\btarget=)([^>]*\bhref="https?:\/\/[^"]*"[^>]*)>/g

export const onRequest = defineMiddleware(async (_context, next) => {
  const response = await next()
  if (!response.headers.get('content-type')?.includes('text/html')) return response
  const html = (await response.text())
    .replace(EXTERNAL, '<a$1 target="_blank">')
    .replace(/<a\b([^>]*\btarget="_blank"[^>]*)>/g, (tag, attrs: string) =>
      /\brel="/.test(attrs) ? tag : `<a${attrs} rel="noopener">`,
    )
  return new Response(html, { status: response.status, headers: response.headers })
})
