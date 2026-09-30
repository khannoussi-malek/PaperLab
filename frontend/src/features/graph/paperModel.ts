import type { LinkKind } from './graphModel'

// The 3D view draws each paper as a small white page, like the website's scroll scene. A page is a textured sprite:
// cheap, but past a few hundred papers the plain spheres read better and keep the frame rate up.
export const PAPER_NODE_LIMIT = 600

export const drawsPapers = (paperCount: number): boolean => paperCount <= PAPER_NODE_LIMIT

/** Pulses running from the citing paper to the cited one, on citations still in focus. */
export const particlesFor = (kind: LinkKind, faded: boolean): number => (kind === 'cites' && !faded ? 2 : 0)
