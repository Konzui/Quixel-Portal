const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld(
  'electronAPI', {
    requestSubmenuData: () => ipcRenderer.send('request-submenu-data'),
    onSubmenuData: (callback) => ipcRenderer.on('submenu-data', callback),
    executeSubmenuAction: (action) => ipcRenderer.send('execute-submenu-action', action),
    closeSubmenu: () => ipcRenderer.send('close-submenu')
  }
);
