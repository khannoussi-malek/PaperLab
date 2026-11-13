/**
 * The only thing PaperLab's pages get from Electron (spec §5): Settings' two desktop switches. contextIsolation and the
 * sandbox keep Node and Electron out of the page; main.ts checks each call's origin and value.
 */
import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'

contextBridge.exposeInMainWorld('paperlabDesktop', {
  getKeepRunning: () => ipcRenderer.invoke('paperlab:get', 'keepRunning'),
  setKeepRunning: (value: boolean) => ipcRenderer.invoke('paperlab:set', 'keepRunning', value),
  getUpdatesEnabled: () => ipcRenderer.invoke('paperlab:get', 'updatesEnabled'),
  setUpdatesEnabled: (value: boolean) => ipcRenderer.invoke('paperlab:set', 'updatesEnabled', value),
  getVoiceEnabled: () => ipcRenderer.invoke('paperlab:voice:get'),
  setVoiceEnabled: (value: boolean) => ipcRenderer.invoke('paperlab:voice:set', value),
  /** Each progress line of turning voice on; the returned function stops listening. */
  onVoiceProgress: (callback: (line: string) => void) => {
    const listener = (_event: IpcRendererEvent, line: string) => callback(line)
    ipcRenderer.on('paperlab:voice:progress', listener)
    return () => {
      ipcRenderer.removeListener('paperlab:voice:progress', listener)
    }
  },
  removeVoiceModels: () => ipcRenderer.invoke('paperlab:voice:remove-models'),
  voiceOutOfMemory: () => ipcRenderer.invoke('paperlab:voice:oom'),
})
