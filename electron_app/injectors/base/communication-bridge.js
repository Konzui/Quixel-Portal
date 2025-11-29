// Communication Bridge - Standardized console.log communication protocol
// This module provides helper functions for sending messages to the Electron main process

module.exports = function() {
  return `
    // ═══════════════════════════════════════════════════════════════
    // 📡 COMMUNICATION BRIDGE - Standardized message protocol
    // ═══════════════════════════════════════════════════════════════
    
    // Message prefixes (backward compatible with QUIXEL_ prefix for now)
    window.PORTAL_MESSAGES = {
      CHECK_ASSET: 'QUIXEL_CHECK_ASSET_EXISTS:',
      IMPORT_ASSET: 'QUIXEL_IMPORT_EXISTING_ASSET:',
      OPEN_EXPLORER: 'QUIXEL_OPEN_EXPLORER:',
      SIGNIN_URL: 'QUIXEL_SIGNIN_URL:',
      DOWNLOAD_START: 'QUIXEL_DOWNLOAD_ATTEMPT_START:'
    };
    
    // Helper function to send messages to Electron main process
    window.sendToElectron = function(messageType, data) {
      const prefix = window.PORTAL_MESSAGES[messageType] || messageType;
      console.log(prefix + data);
    };
  `;
};

