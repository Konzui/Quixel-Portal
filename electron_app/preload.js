const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld(
  'electronAPI', {
    // Navigation
    navigateBack: () => ipcRenderer.send('navigate-back'),
    navigateForward: () => ipcRenderer.send('navigate-forward'),
    navigateHome: () => ipcRenderer.send('navigate-home'),
    navigateReload: () => ipcRenderer.send('navigate-reload'),
    navigateTo: (url) => ipcRenderer.send('navigate-to', url),
    getNavigationState: () => ipcRenderer.invoke('get-navigation-state'),

    // Window controls
    windowMinimize: () => ipcRenderer.send('window-minimize'),
    windowMaximize: () => ipcRenderer.send('window-maximize'),
    windowClose: () => ipcRenderer.send('window-close'),
    startWindowDrag: (x, y) => ipcRenderer.send('start-window-drag', x, y),
    updateWindowDrag: (x, y) => ipcRenderer.send('update-window-drag', x, y),
    endWindowDrag: () => ipcRenderer.send('end-window-drag'),

    // Menu
    showAppMenu: (x, y) => ipcRenderer.send('show-app-menu', x, y),

    // Events
    onNavigationStarted: (callback) => ipcRenderer.on('navigation-started', callback),
    onNavigationFinished: (callback) => ipcRenderer.on('navigation-finished', callback),
    onPageTitleUpdated: (callback) => ipcRenderer.on('page-title-updated', callback),

    // Downloads Panel
    toggleDownloadsPanel: () => ipcRenderer.send('toggle-downloads-panel'),
    setDownloadsPanelState: (isOpen) => ipcRenderer.send('set-downloads-panel-state', isOpen),
    getDownloadHistory: () => ipcRenderer.invoke('get-download-history'),
    getImportHistory: () => ipcRenderer.invoke('get-import-history'),
    openInExplorer: (path) => ipcRenderer.send('open-in-explorer', path),
    onToggleDownloadsPanel: (callback) => ipcRenderer.on('toggle-downloads-panel', callback),
    onDownloadStarted: (callback) => ipcRenderer.on('download-started', callback),
    onDownloadProgress: (callback) => ipcRenderer.on('download-progress-update', callback),
    onDownloadCompleted: (callback) => ipcRenderer.on('download-completed', callback),
    onBlenderImportComplete: (callback) => ipcRenderer.on('blender-import-complete', callback)
  }
);
