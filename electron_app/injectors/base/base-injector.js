// Base Injector - Common initialization and window.electronBridge setup
// Provides the foundation for all website injectors

module.exports = function() {
  return `
    // ═══════════════════════════════════════════════════════════════
    // 🔧 BASE INITIALIZATION - Common setup for all websites
    // ═══════════════════════════════════════════════════════════════
    
    // Create bridge for folder selection and downloads
    window.electronBridge = {
      selectDownloadPath: async function() {
        return new Promise((resolve) => {
          const currentPath = window.quixelDownloadPath || localStorage.getItem('quixelDownloadPath') || 'C:\\\\Users\\\\' + ((typeof process !== 'undefined' && process.env.USERNAME) || 'User') + '\\\\Documents\\\\Quixel Portal';
          const newPath = prompt('Enter download path (or paste full path):', currentPath);
          if (newPath && newPath !== currentPath) {
            resolve(newPath);
          } else {
            resolve(null);
          }
        });
      },

      // Open file explorer at the specified path
      openFileExplorer: function(filePath) {
        // Use console.log with special prefix that main process can listen to
        if (window.sendToElectron) {
          window.sendToElectron('OPEN_EXPLORER', filePath);
        } else {
          console.log('QUIXEL_OPEN_EXPLORER:' + filePath);
        }
      }
    };
    
    // Initialize common window state
    window.currentDownloadButton = null;
    window.downloadButtons = [];
  `;
};

