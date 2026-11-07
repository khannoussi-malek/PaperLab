import { useLayoutEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { NavRail } from '@/components/NavRail'

/**
 * The sidebar's one DOM home for the whole session. Every view draws its own `AppShell`, so a sidebar inside the shell
 * was destroyed and drawn again on every navigation: its glass pill restarted, its workspace list re-rendered and its
 * scroll reset. Instead `PersistentRail` renders the one `NavRail` into this node, and each shell's `RailSlot` moves
 * the node into place. Moving a node doesn't remount what React rendered into it.
 */
let host: HTMLDivElement | null = null
function railHost() {
  if (!host) {
    host = document.createElement('div')
    // `app-rail` (index.css) takes the sidebar out of the page cross-fade, so its pill glides live through it.
    host.className = 'app-rail flex min-h-0 flex-1 flex-col [&>nav]:flex-1'
  }
  return host
}

/**
 * The app's one desktop sidebar. Mount it once, after the routed page (App), so that on a navigation the new page's
 * slot has taken the node before the sidebar measures where its pill goes.
 */
export function PersistentRail() {
  return createPortal(<NavRail />, railHost())
}

/** Where a shell shows the sidebar: the persistent node moves in on mount and out on unmount. */
export function RailSlot() {
  const slot = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const here = slot.current
    if (!here) return
    const node = railHost()
    here.appendChild(node)
    return () => {
      if (node.parentNode === here) here.removeChild(node)
    }
  }, [])
  return <div ref={slot} className="flex min-h-0 flex-1 flex-col" />
}
