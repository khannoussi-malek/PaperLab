import { BASE, SITE } from './site.ts'

// schema.org blocks shared by guides and feature pages.
export const faqPage = (faqs: { q: string; a: string }[]) => ({
  '@context': 'https://schema.org',
  '@type': 'FAQPage',
  mainEntity: faqs.map(({ q, a }) => ({ '@type': 'Question', name: q, acceptedAnswer: { '@type': 'Answer', text: a } })),
})

/** Home › section › page, as BreadcrumbList. `trail` is [name, path] pairs after the home page. */
export const breadcrumbs = (trail: [string, string][]) => ({
  '@context': 'https://schema.org',
  '@type': 'BreadcrumbList',
  itemListElement: [['PaperLab', ''], ...trail].map(([name, path], i) => ({
    '@type': 'ListItem',
    position: i + 1,
    name,
    item: `${SITE}${BASE}${path}`,
  })),
})
