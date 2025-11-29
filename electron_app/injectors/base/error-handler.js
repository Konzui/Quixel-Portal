// Error Handler - Global error handlers for download attempts
// Handles unhandled errors and promise rejections during downloads

module.exports = function() {
  return `
    // ═══════════════════════════════════════════════════════════════
    // 🛡️ GLOBAL ERROR HANDLERS - Catch unhandled errors and promise rejections
    // ═══════════════════════════════════════════════════════════════
    
    // Track if we're in a download attempt
    window.downloadAttemptStartTime = null;
    window.downloadTimeoutId = null;
    
    // Global error handler for unhandled errors
    window.addEventListener('error', function(event) {
      // Check if this error is related to API calls during download
      if (window.downloadAttemptStartTime && event.error) {
        const errorMessage = event.error.message || event.error.toString() || '';
        const errorStack = event.error.stack || '';
        
        // Check for API error patterns
        if (errorMessage.includes('Request failed with status code') ||
            errorMessage.includes('status code 400') ||
            errorMessage.includes('status code 401') ||
            errorMessage.includes('status code 403') ||
            errorMessage.includes('status code 404') ||
            errorMessage.includes('status code 500') ||
            errorMessage.includes('Cannot read properties of undefined') ||
            errorStack.includes('Request failed')) {
          
          const timeSinceAttempt = Date.now() - window.downloadAttemptStartTime;
          if (timeSinceAttempt < 10000) {
            // Clear timeout
            if (window.downloadTimeoutId) {
              clearTimeout(window.downloadTimeoutId);
              window.downloadTimeoutId = null;
            }
            
            // Trigger failure handler
            if (window.onDownloadFailed) {
              window.onDownloadFailed({
                url: window.location.href,
                error: 'API Error: ' + errorMessage
              });
            }
            
            // Reset tracking
            window.downloadAttemptStartTime = null;
          }
        }
      }
    });
    
    // Global handler for unhandled promise rejections
    window.addEventListener('unhandledrejection', function(event) {
      if (window.downloadAttemptStartTime && event.reason) {
        const errorMessage = event.reason.message || event.reason.toString() || '';
        const errorStack = event.reason.stack || '';
        
        // Check for API error patterns
        if (errorMessage.includes('Request failed with status code') ||
            errorMessage.includes('status code 400') ||
            errorMessage.includes('status code 401') ||
            errorMessage.includes('status code 403') ||
            errorMessage.includes('status code 404') ||
            errorMessage.includes('status code 500') ||
            errorMessage.includes('Cannot read properties of undefined') ||
            errorStack.includes('Request failed')) {
          
          const timeSinceAttempt = Date.now() - window.downloadAttemptStartTime;
          if (timeSinceAttempt < 10000) {
            // Clear timeout
            if (window.downloadTimeoutId) {
              clearTimeout(window.downloadTimeoutId);
              window.downloadTimeoutId = null;
            }
            
            // Trigger failure handler
            if (window.onDownloadFailed) {
              window.onDownloadFailed({
                url: window.location.href,
                error: 'API Error: ' + errorMessage
              });
            }
            
            // Reset tracking
            window.downloadAttemptStartTime = null;
            
            // Prevent default error handling
            event.preventDefault();
          }
        }
      }
    });
  `;
};

