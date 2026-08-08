"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electron", {
  /** Opens a native folder-picker dialog. Returns the absolute path or null. */
  selectFolder: () => ipcRenderer.invoke("select-folder"),
  /** Reveals a file in Finder / Explorer. */
  showInFolder: (filePath) => ipcRenderer.invoke("show-item-in-folder", filePath),
  /** True when running inside Electron. */
  isElectron: true,
});
