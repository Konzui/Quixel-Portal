const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld(
  'electronAPI', {
    selectWebsite: (website) => ipcRenderer.send('select-website', website),
    closeDropdown: () => ipcRenderer.send('close-dropdown'),
    executeSubmenuAction: (action) => ipcRenderer.send('execute-submenu-action', action)
  }
);
