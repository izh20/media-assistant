const { contextBridge } = require('electron');

// Minimal preload - the app uses HTTP API, no IPC needed
contextBridge.exposeInMainWorld('electronAPI', {
  platform: process.platform,
  isElectron: true,
});
