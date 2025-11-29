// URL Utils - URL parsing and asset ID extraction
// Provides functions to parse URLs and extract asset identifiers

module.exports = function() {
  return `
    // ═══════════════════════════════════════════════════════════════
    // 🔗 URL UTILITIES - URL parsing and asset ID extraction
    // ═══════════════════════════════════════════════════════════════
    
    // Extract asset ID from URL
    window.extractAssetIdFromUrl = function() {
      const urlParams = new URLSearchParams(window.location.search);
      let assetId = urlParams.get('assetId') || urlParams.get('id');
      
      // Also try to extract from path (e.g., /assets/12345)
      const pathMatch = window.location.pathname.match(/\\/(?:assets|asset)\\/([^/]+)/);
      if (pathMatch) {
        assetId = assetId || pathMatch[1];
      }
      
      return assetId;
    };
    
    // Monitor URL changes
    window.setupUrlObserver = function(callback) {
      let lastUrl = window.location.href;
      const urlObserver = new MutationObserver(() => {
        if (lastUrl !== window.location.href) {
          lastUrl = window.location.href;
          if (callback) callback(lastUrl);
        }
      });

      urlObserver.observe(document.body, {
        childList: true,
        subtree: true
      });
      
      return urlObserver;
    };
  `;
};

