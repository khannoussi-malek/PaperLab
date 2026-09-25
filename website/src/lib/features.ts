// Every PaperLab feature with its own page at /features/<slug>/. Facts come from the README; `next` marks a feature
// that is built and merged but not yet in a desktop release. Nothing planned-but-unbuilt goes here.
import { LIBRARY_FEATURES } from './features/library.ts'
import { READING_FEATURES } from './features/reading.ts'

export type Feature = {
  slug: string
  name: string
  /** One line for cards and lists. */
  tagline: string
  /** <title>, 70 characters at most. */
  title: string
  /** Meta description, 160 characters at most. */
  description: string
  h1: string
  /** The first paragraph: a direct answer a search snippet or an AI assistant can quote whole. */
  answer: string
  /** A README screenshot name from .github/assets, when one shows this feature. */
  shot?: string
  shotAlt?: string
  next?: boolean
  /** What you can do, one sentence each. */
  points: string[]
  steps?: { title: string; body: string }[]
  tips: string[]
  faqs: { q: string; a: string }[]
  /** Slugs of related features: the page links each one. */
  related: string[]
  /** Paths of guides this feature helps with: the feature and the guide link each other. */
  guides: string[]
}

export const FEATURES: Feature[] = [...READING_FEATURES, ...LIBRARY_FEATURES]

export const featureBySlug = (slug: string) => FEATURES.find((feature) => feature.slug === slug)
