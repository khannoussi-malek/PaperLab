import { fetchLatestVersion, fetchStars } from './github'
import { REPO_SLUG } from './site'

// Asked once per build, however many pages use them. The Pages workflow passes GITHUB_TOKEN so a rate limit can't blank them.
const token = process.env.GITHUB_TOKEN
export const stars = await fetchStars(REPO_SLUG, fetch, token)
export const latestVersion = await fetchLatestVersion(REPO_SLUG, fetch, token)
