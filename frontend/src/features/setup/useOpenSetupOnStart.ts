import { useEffect, useRef } from 'react'
import { useSetup } from '@/api/queries'
import { setupHref } from '@/lib/route'
import { openSetupOnStart } from './setup'

/** Opens #/setup once, on start, while the server says setup isn't done (spec §5). Leaving it for another page is
 * allowed; Finish or Skip ends it for good. */
export function useOpenSetupOnStart() {
  const setup = useSetup()
  const decided = useRef(false)
  useEffect(() => {
    if (decided.current || setup.data === undefined) return
    decided.current = true
    if (openSetupOnStart(setup.data.done, window.location.hash)) window.location.hash = setupHref
  }, [setup.data])
}
