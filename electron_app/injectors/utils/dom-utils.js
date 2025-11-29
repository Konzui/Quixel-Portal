// DOM Utils - DOM manipulation helpers
// Provides generic DOM manipulation utilities

module.exports = function() {
  return `
    // ═══════════════════════════════════════════════════════════════
    // 🎯 DOM UTILITIES - Generic DOM manipulation helpers
    // ═══════════════════════════════════════════════════════════════
    
    // Debounce helper
    window.createDebouncer = function(delay) {
      let timeout = null;
      return function(callback) {
        clearTimeout(timeout);
        timeout = setTimeout(callback, delay);
      };
    };
    
    // Setup DOM observer for detecting new elements
    window.setupDOMObserver = function(callback, options) {
      const defaultOptions = {
        childList: true,
        subtree: true
      };
      
      const observer = new MutationObserver((mutations) => {
        if (callback) callback(mutations);
      });
      
      observer.observe(document.body, Object.assign(defaultOptions, options || {}));
      return observer;
    };
  `;
};

