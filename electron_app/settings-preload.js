const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld('settingsAPI', {
  // Close settings window
  closeSettings: () => ipcRenderer.send('close-settings'),

  // Select download path using native dialog
  selectDownloadPath: () => ipcRenderer.invoke('select-download-path'),

  // Get current settings
  getSettings: () => ipcRenderer.invoke('get-settings'),

  // Save settings
  saveSettings: (settings) => ipcRenderer.send('save-settings', settings),

  // Listen for settings updates from main process
  onSettingsUpdated: (callback) => {
    ipcRenderer.on('settings-updated', (event, settings) => callback(settings));
  }
});
