/**
 * The only thing PaperLab's pages get from Electron (spec §5): Settings' two desktop switches. contextIsolation and the
 * sandbox keep Node and Electron out of the page; main.ts checks each call's origin and value.
 */
import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('paperlabDesktop', {
  getKeepRunning: () => ipcRenderer.invoke('paperlab:get', 'keepRunning'),
  setKeepRunning: (value: boolean) => ipcRenderer.invoke('paperlab:set', 'keepRunning', value),
  getUpdatesEnabled: () => ipcRenderer.invoke('paperlab:get', 'updatesEnabled'),
  setUpdatesEnabled: (value: boolean) => ipcRenderer.invoke('paperlab:set', 'updatesEnabled', value),
})
