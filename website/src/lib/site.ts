// Every outside URL the site links to, in one place. A custom domain changes SITE and BASE only.
export const SITE = 'https://paperlab.tn'
export const BASE = '/'
export const REPO_SLUG = 'khannoussi-malek/PaperLab'
export const REPO = `https://github.com/${REPO_SLUG}`
export const RELEASES = `${REPO}/releases/latest`
export const LINKEDIN = 'https://www.linkedin.com/company/os-paperlab'
export const CONTRIBUTING = `${REPO}/blob/main/CONTRIBUTING.md`
/** The person behind PaperLab: his own profile, apart from the PaperLab page in LINKEDIN. */
export const AUTHOR = {
  name: 'Malek Khannoussi',
  site: 'https://www.malekkhannoussi.tn/',
  linkedin: 'https://www.linkedin.com/in/khannoussi-malek/',
  github: 'https://github.com/khannoussi-malek',
}

/** A path inside the site, under the base path: `href('download/')`. */
export const href = (path = '') => `${BASE}${path}`
