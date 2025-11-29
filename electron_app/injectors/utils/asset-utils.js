// Asset Utils - Asset existence checking logic
// Provides functions to check if assets exist locally

module.exports = function() {
  return `
    // ═══════════════════════════════════════════════════════════════
    // 📦 ASSET UTILITIES - Asset existence checking and caching
    // ═══════════════════════════════════════════════════════════════
    
    // Check if asset exists locally (with caching)
    window.checkAssetExists = function(assetId, callback) {
      if (!assetId) {
        if (callback) callback(false, null);
        return;
      }
      
      // Check cache first
      const cacheKey = 'quixel_asset_' + assetId;
      const cachedResult = window[cacheKey];
      
      if (cachedResult !== undefined) {
        // We have a cached result
        if (cachedResult && cachedResult.path) {
          if (callback) callback(true, cachedResult.path);
        } else {
          if (callback) callback(false, null);
        }
        return;
      }
      
      // No cached result - request check from Electron
      window.quixelAssetCheckInProgress = true;
      window.quixelAssetExists = false;
      window.quixelAssetPath = null;
      
      // Send check request
      if (window.sendToElectron) {
        window.sendToElectron('CHECK_ASSET', assetId);
      } else {
        console.log('QUIXEL_CHECK_ASSET_EXISTS:' + assetId);
      }
      
      // Wait for Electron to respond
      const checkInterval = setInterval(() => {
        if (!window.quixelAssetCheckInProgress) {
          clearInterval(checkInterval);
          
          // Cache the result
          const result = window.quixelAssetExists ? { path: window.quixelAssetPath } : false;
          window[cacheKey] = result;
          
          if (callback) {
            callback(window.quixelAssetExists, window.quixelAssetPath);
          }
        }
      }, 10); // Check every 10ms
      
      // Timeout after 200ms - if no response, assume asset doesn't exist
      setTimeout(() => {
        if (window.quixelAssetCheckInProgress) {
          clearInterval(checkInterval);
          window.quixelAssetCheckInProgress = false;
          window[cacheKey] = false;
          
          if (callback) {
            callback(false, null);
          }
        }
      }, 200);
    };
    
    // Import existing asset (skip download)
    window.importExistingAsset = function(assetPath) {
      if (window.sendToElectron) {
        window.sendToElectron('IMPORT_ASSET', assetPath);
      } else {
        console.log('QUIXEL_IMPORT_EXISTING_ASSET:' + assetPath);
      }
    };
  `;
};

