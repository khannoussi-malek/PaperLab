// Checks the built site in dist/: run `npm run build` first (`npm test` does both).
import assert from 'node:assert/strict'
import { existsSync, readFileSync, statSync } from 'node:fs'
import { test } from 'node:test'
import { BASE, LINKEDIN, RELEASES, REPO, SITE } from '../src/lib/site.ts'
import { FEATURES } from '../src/lib/features.ts'
import { TERMS } from '../src/lib/glossary.ts'
import { AUDIENCES } from '../src/lib/audiences.ts'

const dist = new URL('../dist/', import.meta.url)
// Guides answer what people type into a search engine or ask an AI assistant, before they know PaperLab exists.
const GUIDES = [
  'guides/how-to-read-a-research-paper/',
  'guides/how-to-take-notes-on-research-papers/',
  'guides/find-a-free-pdf-of-a-paper/',
  'guides/chat-with-a-pdf-locally/',
  'compare/zotero/',
  'guides/systematic-literature-review/',
  'guides/check-ai-answers-against-sources/',
  'guides/claude-desktop-with-your-papers/',
  'guides/map-your-literature/',
  'compare/ai-pdf-tools/',
  'guides/write-a-related-work-section/',
  'guides/organize-research-papers/',
  'guides/local-llm-for-research/',
  'guides/extract-data-from-papers/',
  'guides/disclose-ai-use-in-research/',
  'compare/obsidian/',
]
const FEATURE_PAGES = FEATURES.map((feature) => `features/${feature.slug}/`)
const TERM_PAGES = TERMS.map((term) => `glossary/${term.slug}/`)
const AUDIENCE_PAGES = AUDIENCES.map((audience) => `for/${audience.slug}/`)
const PAGES = [
  '', 'download/', 'features/', 'systematic-reviews/', 'faq/', 'guides/', 'glossary/', 'about/',
  ...GUIDES, ...FEATURE_PAGES, ...TERM_PAGES, ...AUDIENCE_PAGES,
]
const read = (path) => readFileSync(new URL(path, dist), 'utf8')
const html = (page) => read(`${page}index.html`)
const meta = (doc, attr, name) => doc.match(new RegExp(`<meta ${attr}="${name}" content="([^"]*)"`))?.[1]
const jsonLd = (doc) =>
  [...doc.matchAll(/<script type="application\/ld\+json">(.*?)<\/script>/gs)].map((m) => JSON.parse(m[1]))

test('every page has its own title and description, a canonical URL, social tags and one h1', () => {
  const titles = new Set()
  for (const page of PAGES) {
    const doc = html(page)
    const title = doc.match(/<title>([^<]+)<\/title>/)?.[1]
    assert.ok(title && title.length <= 70, `${page}: title "${title}"`)
    titles.add(title)
    const description = meta(doc, 'name', 'description')
    assert.ok(description && description.length <= 160, `${page}: description`)
    assert.match(doc, new RegExp(`<link rel="canonical" href="${SITE}${BASE}${page}"`), `${page}: canonical`)
    assert.ok(meta(doc, 'property', 'og:image')?.startsWith('https://'), `${page}: og:image`)
    assert.equal(meta(doc, 'name', 'twitter:card'), 'summary_large_image', `${page}: twitter card`)
    assert.equal(doc.match(/<h1[\s>]/g)?.length, 1, `${page}: one h1`)
    assert.match(doc, /<html lang="en"/)
  }
  assert.equal(titles.size, PAGES.length, 'titles are unique')
})

test('every page asks for a star, a LinkedIn follow and a download, each tracked', () => {
  for (const page of PAGES) {
    const doc = html(page)
    assert.match(doc, new RegExp(`href="${REPO}"[^>]*data-goal="star"`), `${page}: star`)
    assert.match(doc, new RegExp(`href="${LINKEDIN}"[^>]*data-goal="linkedin"`), `${page}: follow`)
    assert.match(doc, new RegExp(`href="${RELEASES}"[^>]*data-goal="download"`), `${page}: download`)
  }
})

test('the home page describes the app and the FAQ its questions, as structured data', () => {
  const app = jsonLd(html('')).find((item) => item['@type'] === 'SoftwareApplication')
  assert.equal(app?.name, 'PaperLab')
  assert.equal(app.downloadUrl, RELEASES)
  const faq = jsonLd(html('faq/')).find((item) => item['@type'] === 'FAQPage')
  assert.ok(faq?.mainEntity.length >= 6, 'six or more questions')
  for (const question of faq.mainEntity) assert.ok(html('faq/').includes(question.name), `on the page: ${question.name}`)
})

test('crawlers find the sitemap, and every image a page shows exists', () => {
  assert.match(read('robots.txt'), new RegExp(`Sitemap: ${SITE}${BASE}sitemap-index.xml`))
  assert.ok(existsSync(new URL('sitemap-index.xml', dist)))
  assert.match(read('llms.txt'), /^# PaperLab/)
  for (const page of PAGES) {
    for (const [, src] of html(page).matchAll(/(?:src|srcset)="([^"]+\.(?:png|svg|webp|jpg))"/g)) {
      assert.ok(src.startsWith(BASE), `${page}: ${src} under the base path`)
      assert.ok(existsSync(new URL(src.slice(BASE.length), dist)), `${page}: ${src} exists`)
    }
  }
})

test('every link to another site opens in a new tab, and none leaks the opener', () => {
  for (const page of PAGES) {
    for (const [tag] of html(page).matchAll(/<a\b[^>]*href="https?:\/\/[^"]*"[^>]*>/g)) {
      assert.match(tag, /target="_blank"/, `${page}: ${tag}`)
      assert.match(tag, /rel="[^"]*noopener[^"]*"/, `${page}: ${tag}`)
    }
  }
})

test('Follow on LinkedIn goes to the PaperLab company page', () => {
  assert.equal(LINKEDIN, 'https://www.linkedin.com/company/os-paperlab')
})

test('every guide answers its question in the first paragraph, as an article with its own FAQ', () => {
  for (const page of GUIDES) {
    const doc = html(page)
    const answer = doc.match(/<p class="answer"[^>]*>(.*?)<\/p>/s)?.[1].replace(/<[^>]+>/g, '')
    assert.ok(answer && answer.length > 120 && answer.length < 700, `${page}: a direct answer of a few sentences`)
    assert.ok(doc.indexOf('class="answer"') < doc.indexOf('<h2'), `${page}: the answer comes before any section`)
    const data = jsonLd(doc)
    assert.ok(data.some((item) => item['@type'] === 'Article' && item.headline), `${page}: Article`)
    const faq = data.find((item) => item['@type'] === 'FAQPage')
    assert.ok(faq?.mainEntity.length >= 3, `${page}: three or more questions`)
    assert.ok(data.some((item) => item['@type'] === 'BreadcrumbList'), `${page}: breadcrumbs`)
    assert.match(doc, new RegExp(`href="${BASE}guides/"`), `${page}: links back to the guides`)
  }
})

test('the guides index and llms.txt list every guide', () => {
  const index = html('guides/')
  const llms = read('llms.txt')
  for (const page of GUIDES) {
    assert.match(index, new RegExp(`href="${BASE}${page}"`), `index links ${page}`)
    assert.ok(llms.includes(`${SITE}${BASE}${page}`), `llms.txt lists ${page}`)
  }
  for (const page of FEATURE_PAGES) assert.ok(llms.includes(`${SITE}${BASE}${page}`), `llms.txt lists ${page}`)
})

test('the home page names PaperLab as one entity, with its GitHub and LinkedIn', () => {
  const app = jsonLd(html('')).find((item) => item['@type'] === 'SoftwareApplication')
  assert.deepEqual(app.sameAs, [REPO, LINKEDIN])
})

test('every feature has its own page that answers first, and links to other features and to guides', () => {
  const index = html('features/')
  for (const feature of FEATURES) {
    const page = `features/${feature.slug}/`
    const doc = html(page)
    assert.match(index, new RegExp(`href="${BASE}${page}"`), `the features page links ${page}`)
    const answer = doc.match(/<p class="answer"[^>]*>(.*?)<\/p>/s)?.[1]
    assert.ok(answer && answer.length > 120, `${page}: a direct answer`)
    const data = jsonLd(doc)
    assert.ok(data.find((item) => item['@type'] === 'FAQPage')?.mainEntity.length >= 3, `${page}: FAQ`)
    assert.ok(data.some((item) => item['@type'] === 'BreadcrumbList'), `${page}: breadcrumbs`)
    const featureLinks = new Set([...doc.matchAll(new RegExp(`href="${BASE}features/([a-z-]+)/"`, 'g'))].map((m) => m[1]))
    featureLinks.delete(feature.slug)
    assert.ok(featureLinks.size >= 2, `${page}: links two or more other features`)
    assert.match(doc, new RegExp(`href="${BASE}(guides|compare)/[a-z-]+/"`), `${page}: links a guide`)
    if (feature.next) assert.match(doc, /Next release/, `${page}: says it arrives in the next release`)
  }
})

test('every guide links back to the features it talks about', () => {
  for (const page of GUIDES) {
    assert.match(html(page), new RegExp(`href="${BASE}features/[a-z-]+/"`), `${page}: links a feature`)
  }
})

test('every glossary term has a page that defines it first, and links to features or guides', () => {
  const index = html('glossary/')
  const slugs = new Set(TERMS.map((term) => term.slug))
  for (const term of TERMS) {
    const page = `glossary/${term.slug}/`
    const doc = html(page)
    assert.match(index, new RegExp(`href="${BASE}${page}"`), `the glossary links ${page}`)
    assert.ok(doc.match(/<p class="answer"[^>]*>(.*?)<\/p>/s)?.[1].length > 80, `${page}: a definition first`)
    const defined = jsonLd(doc).find((item) => item['@type'] === 'DefinedTerm')
    assert.equal(defined?.name, term.name, `${page}: DefinedTerm`)
    assert.match(doc, new RegExp(`href="${BASE}(features|guides|compare)/[a-z-]+/"`), `${page}: links a feature or guide`)
    for (const other of term.related) assert.ok(slugs.has(other), `${page}: related term ${other} exists`)
  }
  assert.ok(jsonLd(index).some((item) => item['@type'] === 'DefinedTermSet'), 'glossary: DefinedTermSet')
})

test('every audience page answers first and walks through three or more features, and the home page links it', () => {
  const home = html('')
  for (const audience of AUDIENCES) {
    const page = `for/${audience.slug}/`
    const doc = html(page)
    assert.match(home, new RegExp(`href="${BASE}${page}"`), `home links ${page}`)
    assert.ok(doc.match(/<p class="answer"[^>]*>(.*?)<\/p>/s)?.[1].length > 120, `${page}: a direct answer`)
    const features = new Set([...doc.matchAll(new RegExp(`href="${BASE}features/([a-z-]+)/"`, 'g'))].map((m) => m[1]))
    assert.ok(features.size >= 3, `${page}: links three or more features`)
    assert.ok(jsonLd(doc).find((item) => item['@type'] === 'FAQPage')?.mainEntity.length >= 3, `${page}: FAQ`)
  }
})

test('screenshots on pages are WebP and light enough to load fast', () => {
  const seen = new Set()
  for (const page of PAGES) {
    for (const [, src] of html(page).matchAll(/(?:src|srcset)="([^"]*\/shots\/[^"]+)"/g)) seen.add(src)
  }
  assert.ok(seen.size > 0)
  for (const src of seen) {
    assert.match(src, /\.webp$/, `${src} is WebP`)
    const kb = statSync(new URL(src.slice(BASE.length), dist)).size / 1024
    assert.ok(kb < 200, `${src} is ${Math.round(kb)} KB`)
  }
})

test('a feature with a screenshot shares that screenshot as its preview image', () => {
  for (const feature of FEATURES.filter((f) => f.shot)) {
    const image = meta(html(`features/${feature.slug}/`), 'property', 'og:image')
    assert.equal(image, `${SITE}${BASE}shots/${feature.shot}.png`, feature.slug)
  }
})

test('a missing page offers the way back into the site', () => {
  const doc = read('404.html')
  for (const path of ['', 'features/', 'guides/', 'download/']) assert.match(doc, new RegExp(`href="${BASE}${path}"`))
  assert.match(doc, /<meta name="robots" content="noindex"/)
})

test('guides link to glossary terms from inside their text, and the home page shows the guides', () => {
  for (const page of GUIDES) {
    const body = html(page).split('<div class="body"')[1]?.split('</div>')[0] ?? ''
    assert.match(body, new RegExp(`href="${BASE}glossary/[a-z-]+/"`), `${page}: a glossary link in the text`)
  }
  const home = html('')
  const linked = GUIDES.filter((page) => home.includes(`href="${BASE}${page}"`))
  assert.ok(linked.length >= 3, 'home links three or more guides')
})

test('the about page names the person behind PaperLab, and every guide credits and links him', () => {
  const about = html('about/')
  const person = jsonLd(about).find((item) => item['@type'] === 'Person')
  assert.equal(person?.name, 'Malek Khannoussi')
  assert.ok(person.sameAs.includes('https://www.linkedin.com/in/khannoussi-malek/'), 'links the personal profile')
  for (const page of GUIDES) {
    const doc = html(page)
    assert.match(doc, new RegExp(`href="${BASE}about/"`), `${page}: links the author`)
    const article = jsonLd(doc).find((item) => item['@type'] === 'Article')
    assert.equal(article.author.url, `${SITE}${BASE}about/`, `${page}: author url`)
  }
})

test('the guides index groups guides by topic, and every guide sits in one', () => {
  const index = html('guides/')
  const groups = [...index.matchAll(/<h2[^>]*>([^<]+)<\/h2>/g)].map((m) => m[1])
  assert.ok(groups.length >= 4, `four or more topics, got ${groups}`)
})

test('the site lives at paperlab.tn, and GitHub Pages is told so', () => {
  assert.equal(SITE, 'https://paperlab.tn')
  assert.equal(BASE, '/')
  assert.equal(read('CNAME').trim(), 'paperlab.tn')
  assert.match(html(''), /<link rel="canonical" href="https:\/\/paperlab.tn\/"/)
})
