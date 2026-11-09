import { toParam, type NavEntry } from './navPath'

const split = () => {
  const hash = location.hash
  const i = hash.indexOf('?')
  return { base: i < 0 ? hash : hash.slice(0, i), query: new URLSearchParams(i < 0 ? '' : hash.slice(i + 1)) }
}

export const readNav = () => split().query.get('nav') ?? ''
/** A library paper id from "Navigate from here" on the Papers tab; writeNav swaps it for `nav`. */
export const readNavPaper = () => split().query.get('navPaper') ?? ''

/** Puts the path in the URL's `nav` param without a history entry; Back still leaves the tab. */
export function writeNav(path: NavEntry[]) {
  const { base, query } = split()
  query.delete('nav')
  query.delete('navPaper')
  const rest = [query.toString(), path.length ? `nav=${toParam(path)}` : ''].filter(Boolean).join('&') // ids stay readable: ':' and ',' unescaped
  history.replaceState(history.state, '', `${base}${rest ? `?${rest}` : ''}`)
}
