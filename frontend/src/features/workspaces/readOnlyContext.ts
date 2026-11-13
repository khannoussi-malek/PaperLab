import { createContext, useContext } from 'react'

/** True under a read-only (imported) workspace: its edit controls turn themselves off. WorkspacePage provides it. */
export const ReadOnlyContext = createContext(false)

export const useReadOnlyWorkspace = () => useContext(ReadOnlyContext)
