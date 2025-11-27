const { app, BrowserWindow, BrowserView, ipcMain, Menu, session, dialog, shell, Tray, nativeImage } = require('electron');
const path = require('path');
const os = require('os');
const fs = require('fs');
const extractZip = require('extract-zip');

let mainWindow;
let browserView;
let tray = null;
let isQuitting = false;
let splashWindow = null;
let websiteDropdownWindow = null;
let submenuWindow = null;
let currentSubmenuType = null;

// Store the Blender instance ID passed from command-line
let blenderInstanceId = null;

// Store current website selection
let currentWebsite = 'quixel'; // Default to Quixel

// Website URLs
const WEBSITE_URLS = {
  quixel: 'https://quixel.com/megascans/home',
  polyhaven: 'https://polyhaven.com/all'
};

// Debug flag - set to true to enable verbose logging
const DEBUG_MODE = false;

// Helper function for debug logging
function debugLog(...args) {
  if (DEBUG_MODE) {
    console.log(...args);
  }
}

// ═══════════════════════════════════════════════════════════════
// 🔑 PARSE COMMAND-LINE ARGUMENTS - Get Blender instance ID
// ═══════════════════════════════════════════════════════════════

// Parse command-line arguments to get the Blender instance ID
const args = process.argv.slice(1);
const instanceIndex = args.indexOf('--blender-instance');
if (instanceIndex !== -1 && instanceIndex + 1 < args.length) {
  blenderInstanceId = args[instanceIndex + 1];
  console.log(`🔑 Quixel Portal: Received Blender instance ID: ${blenderInstanceId}`);
} else {
  console.log('⚠️ Quixel Portal: No Blender instance ID provided (backward compatibility mode)');
}

// ═══════════════════════════════════════════════════════════════
// 🚀 MULTI-INSTANCE MODE - Each Blender gets its own Electron
// ═══════════════════════════════════════════════════════════════

// REMOVED: Single instance lock
// Reason: Allow multiple Blender instances to each have their own Electron window
// Each Electron will monitor its Blender's heartbeat and close when Blender closes

// Debug script injection - monitors DOM for download buttons
function injectDebugScript() {
  if (!browserView) return;

  const debugScript = `
    (function() {
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
      
      // ═══════════════════════════════════════════════════════════════
      // 🔒 API REQUEST INTERCEPTION & QUEUING - Prevent race condition
      // ═══════════════════════════════════════════════════════════════
      
      // Debug flag - controls verbose logging (set to true to enable debug logs)
      const DEBUG_AUTH = false;
      
      // Helper function for debug logging (only logs if DEBUG_AUTH is true)
      function debugLog(...args) {
        if (DEBUG_AUTH) {
          console.log(...args);
        }
      }
      
      // Track authentication state
      window.quixelAuthReady = false;
      window.quixelAuthState = 'WAITING'; // WAITING, AUTHENTICATED, TIMEOUT
      window.quixelRequestQueue = [];
      window.quixelAuthCheckStartTime = Date.now();
      window.quixelAuthDetectedTime = null;
      window.quixelFirstApiRequestSent = false; // Track if we've sent a test request
      window.quixelAuthPollingInterval = null; // Track auth polling interval
      const AUTH_GRACE_PERIOD = 500; // 0.5 seconds grace period (very short, we poll actively)
      const AUTH_TIMEOUT = 5000; // 5 seconds max wait
      const AUTH_POLL_INTERVAL = 300; // Poll every 300ms for auth
      
      // Helper function to get timestamp with milliseconds
      function getTimestamp() {
        const now = Date.now();
        const elapsed = now - window.quixelAuthCheckStartTime;
        return '[' + now + 'ms] (+' + elapsed.toFixed(0) + 'ms)';
      }
      
      debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 🔒 Starting API request interception and queuing system');
      debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ⏱️ Grace period: ' + AUTH_GRACE_PERIOD + 'ms, Timeout: ' + AUTH_TIMEOUT + 'ms');
      
      // Function to check if a URL is an API endpoint that requires auth
      function isApiEndpoint(url) {
        if (!url) return false;
        const apiPatterns = [
          '/v1/',
          '/api/v1/',
          'accounts.quixel.com',
          'mhc-api.quixel.com'
        ];
        return apiPatterns.some(pattern => url.includes(pattern));
      }
      
      // Function to check if a URL is an auth endpoint (should NOT be queued)
      function isAuthEndpoint(url) {
        if (!url) return false;
        const authPatterns = [
          '/api/v1/users/',  // User info checks (e.g., /api/v1/users/konartworks@web.de)
          '/api/v1/login',   // Login/refresh endpoints
          '/v1/users/self', // User self endpoint
          'accounts.quixel.com/api/v1/users/', // Account user endpoints
          'accounts.quixel.com/api/v1/login'    // Account login endpoints
        ];
        return authPatterns.some(pattern => url.includes(pattern));
      }
      
      // Function to check if a response indicates successful authentication
      // NEW: Detect auth from ANY successful API response (200 status)
      function isAuthSuccessResponse(url, status) {
        // Any successful API response (200-299) indicates auth is working
        if (!isApiEndpoint(url)) return false;
        return status >= 200 && status < 300;
      }
      
      // Function to actively poll for authentication
      function startAuthPolling() {
        if (window.quixelAuthReady || window.quixelAuthPollingInterval) {
          return; // Already polling or auth ready
        }
        
        debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 🔄 Starting active auth polling (every ' + AUTH_POLL_INTERVAL + 'ms)');
        
        window.quixelAuthPollingInterval = setInterval(() => {
          if (window.quixelAuthReady) {
            clearInterval(window.quixelAuthPollingInterval);
            window.quixelAuthPollingInterval = null;
            return;
          }
          
          // Try a lightweight API endpoint to test auth
          // Use a simple endpoint that should work if auth is ready
          const testUrl = 'https://quixel.com/v1/frontPageContent?webPage=homepage';
          debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 🔍 Polling auth status...');
          
          const testXhr = new window._quixelOriginalXHR();
          testXhr.open('GET', testUrl, true);
          testXhr.addEventListener('readystatechange', function() {
            // Early exit if auth became ready from another request
            if (window.quixelAuthReady) {
              clearInterval(window.quixelAuthPollingInterval);
              window.quixelAuthPollingInterval = null;
              return;
            }
            if (testXhr.readyState === 4) {
              if (isAuthSuccessResponse(testUrl, testXhr.status)) {
                debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 🎉 Auth SUCCESS detected via polling! (status: ' + testXhr.status + ')');
                clearInterval(window.quixelAuthPollingInterval);
                window.quixelAuthPollingInterval = null;
                releaseQueuedRequests('auth_success');
              } else if (testXhr.status === 401) {
                // Still not authenticated, continue polling
                const elapsed = Date.now() - window.quixelAuthCheckStartTime;
                debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ⏳ Still waiting for auth... (elapsed: ' + elapsed.toFixed(0) + 'ms)');
              }
            }
          });
          testXhr.send();
        }, AUTH_POLL_INTERVAL);
      }
      
      // Function to release queued requests
      function releaseQueuedRequests(reason) {
        if (window.quixelAuthReady) {
          // Suppress the warning - it's expected if multiple requests detect auth simultaneously
          return;
        }
        
        window.quixelAuthReady = true;
        // Stop any active polling
        if (window.quixelAuthPollingInterval) {
          clearInterval(window.quixelAuthPollingInterval);
          window.quixelAuthPollingInterval = null;
        }
        const queueLength = window.quixelRequestQueue.length;
        const timeElapsed = Date.now() - window.quixelAuthCheckStartTime;
        
        // Update state based on reason
        if (reason === 'auth_success') {
          window.quixelAuthState = 'AUTHENTICATED';
          window.quixelAuthDetectedTime = Date.now();
          const totalTime = (window.quixelAuthDetectedTime - window.quixelAuthCheckStartTime).toFixed(2);
          debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 🎉 Authentication SUCCESS detected! (Total time: ' + totalTime + 'ms) Releasing ' + queueLength + ' queued request(s)');
        } else if (reason === 'timeout') {
          window.quixelAuthState = 'TIMEOUT';
          debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ⏰ Grace period ended without auth confirmation (Total time: ' + timeElapsed.toFixed(2) + 'ms). Releasing ' + queueLength + ' queued request(s) anyway (timeout fallback)');
        } else {
          window.quixelAuthState = 'TIMEOUT';
          debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ⏱️ Releasing ' + queueLength + ' queued request(s) (' + (reason || 'unknown reason') + ', Total time: ' + timeElapsed.toFixed(2) + 'ms)');
        }
        
        // Process all queued requests
        window.quixelRequestQueue.forEach((queuedRequest, index) => {
          debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 📤 Releasing queued request #' + (index + 1) + ': ' + queuedRequest.url);
          
          if (queuedRequest.type === 'fetch') {
            // Execute the original fetch
            queuedRequest.originalFetch(queuedRequest.url, queuedRequest.options)
              .then(response => {
                debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ✅ Queued fetch completed: ' + queuedRequest.url + ' (status: ' + response.status + ')');
                queuedRequest.resolve(response);
              })
              .catch(error => {
                debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ❌ Queued fetch failed: ' + queuedRequest.url + ' - ' + error.message);
                queuedRequest.reject(error);
              });
          } else if (queuedRequest.type === 'xhr') {
            // Execute the queued XHR
            // Note: open() was already called when queuing, so XHR is in OPENED state
            // We just need to send it now
            try {
              // Remove queued flag
              delete queuedRequest.xhr._quixelQueued;
              
              // Headers should already be set (we set them when queuing)
              // But restore any additional headers that might have been set
              if (queuedRequest.headers) {
                Object.keys(queuedRequest.headers).forEach(header => {
                  try {
                    queuedRequest.xhr.setRequestHeader(header, queuedRequest.headers[header]);
                  } catch (e) {
                    // Header might already be set, ignore
                  }
                });
              }
              
              // Restore event handlers
              if (queuedRequest.onload) queuedRequest.xhr.onload = queuedRequest.onload;
              if (queuedRequest.onerror) queuedRequest.xhr.onerror = queuedRequest.onerror;
              if (queuedRequest.onreadystatechange) queuedRequest.xhr.onreadystatechange = queuedRequest.onreadystatechange;
              
              // No need to monitor auth success for queued requests - auth is already confirmed
              // (We're releasing them because auth is ready)
              
              // Now send the request (XHR is already in OPENED state)
              queuedRequest.xhr.send(queuedRequest.body);
              debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ✅ Queued XHR sent: ' + queuedRequest.url);
            } catch (error) {
              debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ❌ Queued XHR failed: ' + queuedRequest.url + ' - ' + error.message);
              if (queuedRequest.onerror) queuedRequest.onerror();
            }
          }
        });
        
        // Clear the queue
        window.quixelRequestQueue = [];
      }
      
      // Monitor fetch responses to detect successful authentication
      const originalFetch = window.fetch;
      window.fetch = function(url, options) {
        const fetchUrl = typeof url === 'string' ? url : url.url || url.toString();
        
        // Check if this is an API endpoint
        if (isApiEndpoint(fetchUrl)) {
          // If it's an auth endpoint, allow it through immediately and monitor response
          if (isAuthEndpoint(fetchUrl)) {
            debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 🔐 Auth endpoint detected, allowing immediately: ' + fetchUrl);
            return originalFetch.apply(this, arguments).then(response => {
              // Monitor for auth success
              if (isAuthSuccessResponse(fetchUrl, response.status)) {
                debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 🎉 Auth SUCCESS! Detected 200 response from: ' + fetchUrl);
                releaseQueuedRequests('auth_success');
              } else if (response.status === 401) {
                debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ⚠️ Auth endpoint returned 401 (not authenticated yet): ' + fetchUrl);
                // Start polling for auth
                startAuthPolling();
              } else {
                debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ℹ️ Auth endpoint response: ' + fetchUrl + ' (status: ' + response.status + ')');
              }
              return response;
            }).catch(error => {
              debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ❌ Auth endpoint error: ' + fetchUrl + ' - ' + error.message);
              throw error;
            });
          }
          
          // Regular API endpoint - check if we should queue it
          debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 🔍 Intercepted API fetch: ' + fetchUrl);
          
          // If auth is ready, proceed normally (no monitoring needed)
          if (window.quixelAuthReady) {
            debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ✅ Auth ready, allowing fetch: ' + fetchUrl);
            return originalFetch.apply(this, arguments);
          }
          
          // Allow first API request through immediately to test auth
          if (!window.quixelFirstApiRequestSent) {
            window.quixelFirstApiRequestSent = true;
            debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 🧪 First API request - allowing through to test auth: ' + fetchUrl);
            return originalFetch.apply(this, arguments).then(response => {
              // Early exit if auth became ready from another request
              if (window.quixelAuthReady) return response;
              if (isAuthSuccessResponse(fetchUrl, response.status)) {
                debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 🎉 Auth SUCCESS detected from first fetch response! ' + fetchUrl + ' (status: ' + response.status + ')');
                releaseQueuedRequests('auth_success');
              } else if (response.status === 401) {
                debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ⚠️ First request returned 401 (auth not ready), will queue subsequent requests');
                // Start polling for auth
                startAuthPolling();
              }
              return response;
            });
          }
          
            // Check if grace period has passed
            const timeSinceStart = Date.now() - window.quixelAuthCheckStartTime;
            if (timeSinceStart >= AUTH_GRACE_PERIOD) {
              debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ⏱️ Grace period passed (' + timeSinceStart.toFixed(0) + 'ms), allowing fetch: ' + fetchUrl);
              // Check auth one more time before allowing
              if (window.quixelAuthReady) {
                return originalFetch.apply(this, arguments);
              }
              // Monitor response for auth success only if not ready yet
              return originalFetch.apply(this, arguments).then(response => {
                if (window.quixelAuthReady) return response; // Early exit if auth became ready
                if (isAuthSuccessResponse(fetchUrl, response.status)) {
                  debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 🎉 Auth SUCCESS detected from fetch response! ' + fetchUrl + ' (status: ' + response.status + ')');
                  releaseQueuedRequests('auth_success');
                }
                return response;
              });
            }
          
          // Queue the request
          const remainingTime = (AUTH_GRACE_PERIOD - timeSinceStart).toFixed(0);
          debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 📥 Queuing fetch request: ' + fetchUrl + ' (waiting for auth, ' + remainingTime + 'ms remaining)');
          
          return new Promise((resolve, reject) => {
            window.quixelRequestQueue.push({
              type: 'fetch',
              url: fetchUrl,
              options: options,
              originalFetch: originalFetch.bind(window),
              resolve: resolve,
              reject: reject
            });
          });
        }
        
        // Non-API requests proceed normally
        return originalFetch.apply(this, arguments);
      };
      
      // Monitor XMLHttpRequest to detect successful authentication
      const OriginalXHR = window.XMLHttpRequest;
      
      // Store OriginalXHR globally for polling function
      window._quixelOriginalXHR = OriginalXHR;
      
      window.XMLHttpRequest = function() {
        const xhr = new OriginalXHR();
        const originalOpen = xhr.open;
        const originalSend = xhr.send;
        const originalSetRequestHeader = xhr.setRequestHeader;
        
        let requestUrl = null;
        let requestMethod = null;
        let requestAsync = true;
        let requestUser = null;
        let requestPassword = null;
        let requestHeaders = {};
        let requestBody = null;
        let onloadHandler = null;
        let onerrorHandler = null;
        let onreadystatechangeHandler = null;
        
        // Intercept open
        xhr.open = function(method, url, async, user, password) {
          requestMethod = method;
          requestUrl = url;
          requestAsync = async !== undefined ? async : true;
          requestUser = user;
          requestPassword = password;
          
          // Check if this is an API endpoint
          if (isApiEndpoint(url)) {
            // If it's an auth endpoint, allow it through immediately and monitor response
            if (isAuthEndpoint(url)) {
              // Skip if auth already ready
              if (window.quixelAuthReady) {
                return originalOpen.call(this, method, url, async, user, password);
              }
              debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 🔐 Auth endpoint detected, allowing immediately: ' + method + ' ' + url);
              const result = originalOpen.call(this, method, url, async, user, password);
              // Add monitoring for auth success (only once, use flag to prevent duplicates)
              if (!xhr._quixelAuthListenerAdded) {
                xhr._quixelAuthListenerAdded = true;
                const authListener = function() {
                  // Early exit checks - must be first thing in listener
                  if (window.quixelAuthReady) {
                    xhr.removeEventListener('readystatechange', authListener);
                    return;
                  }
                  if (xhr.readyState !== 4) return;
                  // Double-check auth state before processing
                  if (window.quixelAuthReady) {
                    xhr.removeEventListener('readystatechange', authListener);
                    return;
                  }
                  
                  if (isAuthSuccessResponse(url, xhr.status)) {
                    // Final check before logging
                    if (window.quixelAuthReady) {
                      xhr.removeEventListener('readystatechange', authListener);
                      return;
                    }
                    debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 🎉 Auth SUCCESS! Detected 200 response from: ' + url);
                    releaseQueuedRequests('auth_success');
                    // Remove listener after detecting auth
                    xhr.removeEventListener('readystatechange', authListener);
                  } else if (xhr.status === 401) {
                    if (window.quixelAuthReady) {
                      xhr.removeEventListener('readystatechange', authListener);
                      return;
                    }
                    debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ⚠️ Auth endpoint returned 401 (not authenticated yet): ' + url);
                    // Start polling for auth
                    startAuthPolling();
                  } else {
                    if (window.quixelAuthReady) {
                      xhr.removeEventListener('readystatechange', authListener);
                      return;
                    }
                    debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ℹ️ Auth endpoint response: ' + url + ' (status: ' + xhr.status + ')');
                  }
                };
                xhr.addEventListener('readystatechange', authListener);
              }
              return result;
            }
            
            // Regular API endpoint
            debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 🔍 Intercepted API XHR: ' + method + ' ' + url);
            
            // If auth is ready, proceed normally (no monitoring needed)
            if (window.quixelAuthReady) {
              debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ✅ Auth ready, allowing XHR: ' + url);
              return originalOpen.call(this, method, url, async, user, password);
            }
            
            // Allow first API request through immediately to test auth
            if (!window.quixelFirstApiRequestSent) {
              window.quixelFirstApiRequestSent = true;
              debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 🧪 First API request - allowing through to test auth: ' + method + ' ' + url);
              const result = originalOpen.call(this, method, url, async, user, password);
              // Monitor response for auth success (only once, use flag to prevent duplicates)
              if (!xhr._quixelAuthListenerAdded) {
                xhr._quixelAuthListenerAdded = true;
                const authListener = function() {
                  // Early exit checks - must be first thing in listener
                  if (window.quixelAuthReady) {
                    xhr.removeEventListener('readystatechange', authListener);
                    return;
                  }
                  if (xhr.readyState !== 4) return;
                  // Double-check auth state before processing
                  if (window.quixelAuthReady) {
                    xhr.removeEventListener('readystatechange', authListener);
                    return;
                  }
                  
                  if (isAuthSuccessResponse(url, xhr.status)) {
                    // Final check before logging
                    if (window.quixelAuthReady) {
                      xhr.removeEventListener('readystatechange', authListener);
                      return;
                    }
                    debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 🎉 Auth SUCCESS detected from first XHR response! ' + url + ' (status: ' + xhr.status + ')');
                    releaseQueuedRequests('auth_success');
                    // Remove listener after detecting auth
                    xhr.removeEventListener('readystatechange', authListener);
                  } else if (xhr.status === 401) {
                    if (window.quixelAuthReady) {
                      xhr.removeEventListener('readystatechange', authListener);
                      return;
                    }
                    debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ⚠️ First request returned 401 (auth not ready), will queue subsequent requests');
                    // Start polling for auth
                    startAuthPolling();
                  }
                };
                xhr.addEventListener('readystatechange', authListener);
              }
              return result;
            }
            
            // Check if grace period has passed
            const timeSinceStart = Date.now() - window.quixelAuthCheckStartTime;
            if (timeSinceStart >= AUTH_GRACE_PERIOD) {
              debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ⏱️ Grace period passed (' + timeSinceStart.toFixed(0) + 'ms), allowing XHR: ' + url);
              // Check auth one more time before allowing
              if (window.quixelAuthReady) {
                return originalOpen.call(this, method, url, async, user, password);
              }
              const result = originalOpen.call(this, method, url, async, user, password);
              // Only monitor if auth is not ready yet and listener not already added
              if (!window.quixelAuthReady && !xhr._quixelAuthListenerAdded) {
                xhr._quixelAuthListenerAdded = true;
                const authListener = function() {
                  // Early exit checks - must be first thing in listener
                  if (window.quixelAuthReady) {
                    xhr.removeEventListener('readystatechange', authListener);
                    return;
                  }
                  if (xhr.readyState !== 4) return;
                  // Double-check auth state before processing
                  if (window.quixelAuthReady) {
                    xhr.removeEventListener('readystatechange', authListener);
                    return;
                  }
                  
                  if (isAuthSuccessResponse(url, xhr.status)) {
                    // Final check before logging
                    if (window.quixelAuthReady) {
                      xhr.removeEventListener('readystatechange', authListener);
                      return;
                    }
                    debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 🎉 Auth SUCCESS detected from XHR response! ' + url + ' (status: ' + xhr.status + ')');
                    releaseQueuedRequests('auth_success');
                    // Remove listener after detecting auth
                    xhr.removeEventListener('readystatechange', authListener);
                  }
                };
                xhr.addEventListener('readystatechange', authListener);
              }
              return result;
            }
            
            // Queue the request - but we need to call open() to put XHR in OPENED state
            // Otherwise send() will fail with "state must be OPENED" error
            const remainingTime = (AUTH_GRACE_PERIOD - timeSinceStart).toFixed(0);
            debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 📥 Queuing XHR request: ' + url + ' (waiting for auth, ' + remainingTime + 'ms remaining)');
            isQueued = true;
            // Mark that this request is queued
            xhr._quixelQueued = true;
            // Actually call open() to put XHR in OPENED state (required for send() to work)
            // But we'll intercept send() to queue it instead
            return originalOpen.call(this, method, url, async, user, password);
          }
          
          // Non-API requests proceed normally
          return originalOpen.call(this, method, url, async, user, password);
        };
        
        // Intercept setRequestHeader
        xhr.setRequestHeader = function(header, value) {
          // If request is queued, store headers but also set them (XHR is in OPENED state)
          if (requestUrl && isApiEndpoint(requestUrl) && xhr._quixelQueued && !window.quixelAuthReady) {
            requestHeaders[header] = value;
            // Also set the header on the XHR since it's already opened
            return originalSetRequestHeader.call(this, header, value);
          }
          return originalSetRequestHeader.call(this, header, value);
        };
        
        // Intercept send
        xhr.send = function(body) {
          requestBody = body;
          
          if (requestUrl && isApiEndpoint(requestUrl)) {
            // If it's an auth endpoint, it should have already been opened and allowed through
            // Just send it normally (monitoring was added in open())
            if (isAuthEndpoint(requestUrl)) {
              return originalSend.call(this, body);
            }
            
            // Regular API endpoint
            // If auth is ready, proceed normally (no monitoring needed)
            if (window.quixelAuthReady) {
              debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ✅ Auth ready, sending XHR: ' + requestUrl);
              return originalSend.call(this, body);
            }
            
            // If this is the first request and it was already opened, just send it
            // (monitoring was already added in open())
            // Note: isQueued is set in open() if the request was queued
            if (window.quixelFirstApiRequestSent) {
              // Check if request was queued by checking if open was called
              // If we're here and it's the first request, it means open() already executed
              return originalSend.call(this, body);
            }
            
            // Check if grace period has passed
            const timeSinceStart = Date.now() - window.quixelAuthCheckStartTime;
            if (timeSinceStart >= AUTH_GRACE_PERIOD) {
              debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ⏱️ Grace period passed, sending XHR: ' + requestUrl);
              // Check auth one more time
              if (window.quixelAuthReady) {
                return originalSend.call(this, body);
              }
              // Need to call open first if we queued it
              originalOpen.call(this, requestMethod, requestUrl, requestAsync, requestUser, requestPassword);
              // Restore headers
              Object.keys(requestHeaders).forEach(header => {
                originalSetRequestHeader.call(this, header, requestHeaders[header]);
              });
              // No monitoring needed - auth should be ready or will be detected elsewhere
              // (Listener was already added in open() if needed)
              return originalSend.call(this, body);
            }
            
            // Check if this request was queued
            if (xhr._quixelQueued && !window.quixelAuthReady) {
              // Request was queued, store it properly
              debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 📥 Queuing XHR send: ' + requestUrl);
              
              // Store event handlers (they may have been set after open())
              if (xhr.onload) onloadHandler = xhr.onload;
              if (xhr.onerror) onerrorHandler = xhr.onerror;
              if (xhr.onreadystatechange) onreadystatechangeHandler = xhr.onreadystatechange;
              
              // Store all event listeners that were added
              const listeners = [];
              // Note: We can't easily get all event listeners, so we'll restore the ones we know about
              
              window.quixelRequestQueue.push({
                type: 'xhr',
                url: requestUrl,
                method: requestMethod,
                async: requestAsync,
                user: requestUser,
                password: requestPassword,
                headers: requestHeaders,
                body: body,
                xhr: xhr,
                onload: onloadHandler,
                onerror: onerrorHandler,
                onreadystatechange: onreadystatechangeHandler,
                listeners: listeners
              });
              
              // Don't send yet - wait for auth
              return;
            }
            
            // If request was queued but auth is now ready, send it
            if (xhr._quixelQueued && window.quixelAuthReady) {
              debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ✅ Auth ready, sending previously queued XHR: ' + requestUrl);
              // Remove queued flag
              delete xhr._quixelQueued;
              return originalSend.call(this, body);
            }
          }
          
          // Non-API requests proceed normally
          return originalSend.call(this, body);
        };
        
        return xhr;
      };
      
      // Timeout fallback - release requests after timeout even if auth not confirmed
      setTimeout(() => {
        if (!window.quixelAuthReady) {
          const timeSinceStart = Date.now() - window.quixelAuthCheckStartTime;
          debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ⏰ Maximum timeout reached (' + timeSinceStart.toFixed(2) + 'ms), releasing queued requests anyway');
          releaseQueuedRequests('timeout');
        }
      }, AUTH_TIMEOUT);
      
      // Grace period fallback - release requests after grace period
      setTimeout(() => {
        if (!window.quixelAuthReady) {
          const timeSinceStart = Date.now() - window.quixelAuthCheckStartTime;
          debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ⏱️ Grace period ended (' + timeSinceStart.toFixed(2) + 'ms), releasing queued requests (auth not yet confirmed)');
          releaseQueuedRequests('timeout');
        }
      }, AUTH_GRACE_PERIOD);
      
      debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ✅ API interception system initialized');
      
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
          console.log('QUIXEL_OPEN_EXPLORER:' + filePath);
        }
      };

      // Inject CSS for instant custom background on download buttons + hide annoying popup
      const styleElement = document.createElement('style');
      styleElement.id = 'quixel-download-style';
      styleElement.textContent = \`
        /* Target download buttons - will apply instantly when they appear */
        button.Button___1mkoh.Button--fullWidth___2subI {
          background: #0C8CE9 !important;
          background-color: #0C8CE9 !important;
          color: white !important;
          border: 2px solid #0C8CE9 !important;
          border-color: #0C8CE9 !important;
        }

        /* Hide the annoying "A NEW HOME FOR MEGASCANS" popup */
        div.modalContent___1Vd1b {
          display: none !important;
        }

        /* Also hide the modal overlay/backdrop */
        [class*="modalOverlay"],
        [class*="Modal"],
        div[class*="modal"][class*="Overlay"] {
          display: none !important;
        }

        /* Hide the annoying "Megascans have a new home on Fab" banner */
        div.css-1uaj9x {
          display: none !important;
        }

        /* Also target parent container if needed */
        div.css-1ymlmsw {
          display: none !important;
        }

        /* Linear progress bar styles */
        .quixel-linear-progress-container {
          position: absolute;
          bottom: -2px;
          left: 0;
          width: 100%;
          height: 2px;
          background: rgba(255, 255, 255, 0.1);
          overflow: visible;
        }

        .quixel-linear-progress-fill {
          height: 100%;
          background: rgba(255, 255, 255, 0.8);
          width: 0%;
          transition: width 0.3s ease;
        }

        .quixel-linear-progress-text {
          position: absolute;
          right: 0;
          bottom: 4px;
          font-size: 11px;
          color: rgba(255, 255, 255, 0.7);
          font-weight: 500;
          pointer-events: none;
          white-space: nowrap;
        }

        /* Download notification styles */
        #quixel-download-notification {
          position: fixed;
          bottom: 20px;
          left: 20px;
          background: #1a1a1a;
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 6px;
          padding: 10px 14px;
          padding-right: 32px;
          min-width: 250px;
          max-width: 350px;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
          z-index: 10000;
          opacity: 0;
          transform: translateY(20px);
          transition: opacity 0.3s ease, transform 0.3s ease;
          pointer-events: none;
        }

        #quixel-download-notification.show {
          opacity: 1;
          transform: translateY(0);
          pointer-events: auto;
        }
        
        /* Close button for notification */
        #quixel-download-notification .notification-close {
          position: absolute;
          top: 8px;
          right: 8px;
          width: 20px;
          height: 20px;
          cursor: pointer;
          opacity: 0.6;
          transition: opacity 0.2s;
          display: flex;
          align-items: center;
          justify-content: center;
          border: none;
          background: transparent;
          padding: 0;
        }
        
        #quixel-download-notification .notification-close:hover {
          opacity: 1;
        }
        
        #quixel-download-notification .notification-close::before,
        #quixel-download-notification .notification-close::after {
          content: '';
          position: absolute;
          width: 12px;
          height: 2px;
          background: rgba(255, 255, 255, 0.8);
          border-radius: 1px;
        }
        
        #quixel-download-notification .notification-close::before {
          transform: rotate(45deg);
        }
        
        #quixel-download-notification .notification-close::after {
          transform: rotate(-45deg);
        }

        #quixel-download-notification .notification-title {
          color: rgba(255, 255, 255, 0.9);
          font-size: 13px;
          font-weight: 500;
          margin-bottom: 4px;
        }

        #quixel-download-notification .notification-message {
          color: rgba(255, 255, 255, 0.7);
          font-size: 12px;
          margin-bottom: 4px;
        }

        #quixel-download-notification .notification-path {
          color: rgba(255, 255, 255, 0.8);
          font-size: 11px;
          cursor: pointer;
          text-decoration: underline;
          text-decoration-color: rgba(255, 255, 255, 0.3);
          transition: text-decoration-color 0.2s;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        #quixel-download-notification .notification-path:hover {
          text-decoration-color: rgba(255, 255, 255, 0.6);
        }

        /* Notification with thumbnail */
        #quixel-download-notification .notification-content-with-thumb {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        #quixel-download-notification .notification-thumbnail {
          width: 48px;
          height: 48px;
          object-fit: cover;
          border-radius: 4px;
          flex-shrink: 0;
        }

        #quixel-download-notification .notification-text {
          flex: 1;
          min-width: 0;
        }

        /* Animated dots for "Importing..." */
        @keyframes dotAnimation {
          0%, 20% { content: '.'; }
          40% { content: '..'; }
          60%, 100% { content: '...'; }
        }

        .animated-dots::after {
          content: '...';
          animation: dotAnimation 1.5s infinite;
        }
      \`;
      document.head.appendChild(styleElement);

      // Function to aggressively remove the Megascans popup
      function removeMegascansPopup() {
        let removed = false;

        // Remove the modal popup
        const modalContent = document.querySelector('div.modalContent___1Vd1b');
        if (modalContent) {
          // Try to find and remove the parent modal
          let parent = modalContent.parentElement;
          while (parent && parent !== document.body) {
            if (parent.className && (
                parent.className.includes('modal') ||
                parent.className.includes('Modal') ||
                parent.className.includes('overlay') ||
                parent.className.includes('Overlay')
            )) {
              parent.remove();
              removed = true;
              break;
            }
            parent = parent.parentElement;
          }
          // If no modal parent found, just remove the content
          if (!removed && modalContent.parentElement) {
            modalContent.remove();
            removed = true;
          }
        }

        // Remove the Fab banner
        const fabBanner = document.querySelector('div.css-1uaj9x');
        if (fabBanner) {
          fabBanner.remove();
          removed = true;
        }

        // Also check for parent container
        const fabBannerParent = document.querySelector('div.css-1ymlmsw');
        if (fabBannerParent) {
          fabBannerParent.remove();
          removed = true;
        }

        return removed;
      }

      // Remove popup and banner immediately if they exist
      removeMegascansPopup();

      // Monitor DOM for popup appearing and remove it
      const popupObserver = new MutationObserver(() => {
        removeMegascansPopup();
      });

      popupObserver.observe(document.body, {
        childList: true,
        subtree: true
      });

      // Also check periodically for the first 5 seconds (catches late-loading popups)
      let popupCheckCount = 0;
      const popupCheckInterval = setInterval(() => {
        removeMegascansPopup();
        popupCheckCount++;
        if (popupCheckCount >= 10) { // 10 checks * 500ms = 5 seconds
          clearInterval(popupCheckInterval);
        }
      }, 500);


      // Auto sign-in redirect on startup (one-time check)
      function checkAndRedirectToSignIn() {
        // Only run once
        if (window.signInCheckComplete) {
          return;
        }

        const signInButton = document.querySelector('button.css-xwv3p2');
        if (signInButton && signInButton.textContent.toLowerCase().includes('sign in')) {
          // Listen for URL changes to see where it redirects
          const originalPushState = history.pushState;
          history.pushState = function(...args) {
            return originalPushState.apply(this, arguments);
          };

          const originalReplaceState = history.replaceState;
          history.replaceState = function(...args) {
            return originalReplaceState.apply(this, arguments);
          };

          // Click the sign-in button
          signInButton.click();

          // Check URL after click
          setTimeout(() => {
            const newUrl = window.location.href;
            // Send the sign-in URL to console with special prefix for main process to detect
            console.log('QUIXEL_SIGNIN_URL:' + newUrl);
          }, 100);

          setTimeout(() => {
            const newUrl = window.location.href;
            // Send again in case it changed
            console.log('QUIXEL_SIGNIN_URL:' + newUrl);
          }, 500);

          setTimeout(() => {
            const newUrl = window.location.href;

            // Final check
            console.log('QUIXEL_SIGNIN_URL:' + newUrl);
          }, 1000);

          // Mark as complete so we don't check again
          window.signInCheckComplete = true;
        }
      }

      // Check for sign-in button after a short delay (let page load first)
      setTimeout(() => {
        checkAndRedirectToSignIn();
      }, 1000);

      // Also check a few more times in case the button loads late
      setTimeout(() => {
        checkAndRedirectToSignIn();
      }, 2000);

      setTimeout(() => {
        checkAndRedirectToSignIn();
      }, 3000);

      // Debounce helper to prevent duplicate searches
      let searchTimeout = null;
      let lastSearchTime = 0;

      // Function to add linear progress indicator below download button
      function addProgressBarToButton(button) {
        // Check if progress indicator already exists
        if (button.querySelector('.quixel-linear-progress-container')) {
          return;
        }

        // Make button position relative if not already
        if (window.getComputedStyle(button).position === 'static') {
          button.style.position = 'relative';
        }

        // Create linear progress container
        const progressContainer = document.createElement('div');
        progressContainer.className = 'quixel-linear-progress-container';
        
        // Create progress fill bar
        const progressFill = document.createElement('div');
        progressFill.className = 'quixel-linear-progress-fill';
        
        // Create progress text (percentage)
        const progressText = document.createElement('div');
        progressText.className = 'quixel-linear-progress-text';
        progressText.textContent = '0%';
        
        progressContainer.appendChild(progressFill);
        progressContainer.appendChild(progressText);
        button.appendChild(progressContainer);
        button.dataset.quixelDownloading = 'true';
      }

      // Function to update linear progress
      function updateProgressBar(button, progress) {
        const progressFill = button.querySelector('.quixel-linear-progress-fill');
        const progressText = button.querySelector('.quixel-linear-progress-text');
        
        if (progressFill) {
          progressFill.style.width = progress + '%';
        }
        
        if (progressText) {
          progressText.textContent = Math.round(progress) + '%';
        }
      }

      // Function to remove progress bar
      function removeProgressBar(button) {
        const progressContainer = button.querySelector('.quixel-linear-progress-container');
        if (progressContainer) {
          progressContainer.remove();
        }
        delete button.dataset.quixelDownloading;
      }

      // Silent button detection (no visual debugging)
      window.findDownloadButton = function(skipDebounce = false) {
        // Debounce: only search once per 500ms
        const now = Date.now();
        if (!skipDebounce && now - lastSearchTime < 500) {
          return;
        }
        lastSearchTime = now;

        // Strategy: Look for buttons with "download" or "export" text
        const buttons = Array.from(document.querySelectorAll('button, a, [role="button"]'));
        const foundButtons = buttons.filter(btn => {
          const text = btn.textContent.toLowerCase();
          return text.includes('download') || text.includes('export');
        });

        if (foundButtons.length > 0) {
          // Store references and modify button text
          if (!window.downloadButtons) window.downloadButtons = [];
          foundButtons.forEach((btn, index) => {
            window.downloadButtons[index] = btn;

            // Skip if already processed
            if (btn.dataset.quixelProcessed) return;
            btn.dataset.quixelProcessed = 'true';

            // Change "Download" to "Import to Blender"
            if (btn.textContent.toLowerCase().includes('download')) {
              // Try multiple selectors to find the text element
              let textElement = btn.querySelector('.label') ||
                               btn.querySelector('span') ||
                               btn.querySelector('div') ||
                               btn;

              // Find the deepest text node that contains "download"
              const allTextElements = [textElement];
              const children = textElement.querySelectorAll('*');
              children.forEach(child => {
                if (child.textContent.toLowerCase().includes('download')) {
                  allTextElements.push(child);
                }
              });

              // Use the element with the shortest text content (most specific)
              textElement = allTextElements.reduce((shortest, current) => {
                return current.textContent.length < shortest.textContent.length ? current : shortest;
              }, textElement);

              // Change the text
              if (textElement.textContent.toLowerCase().trim().includes('download')) {
                textElement.textContent = 'Import to Blender';

                // Store reference to the text element
                btn.dataset.textElement = 'true';
                btn._textElement = textElement;
              }

              // Store original text for later restoration
              if (!btn.dataset.originalText) {
                btn.dataset.originalText = 'Import to Blender';
              }

              // Add click handler - use CAPTURE phase (true) to run BEFORE Quixel's handlers
              // This allows us to check if asset exists locally and prevent API call
              const clickHandler = function(e) {
                // Extract asset ID from URL to check if asset exists locally
                const urlParams = new URLSearchParams(window.location.search);
                const assetId = urlParams.get('assetId') || urlParams.get('id');
                
                // Also try to extract from path (e.g., /assets/12345)
                let assetIdFromPath = null;
                const pathMatch = window.location.pathname.match(/\\/(?:assets|asset)\\/([^/]+)/);
                if (pathMatch) {
                  assetIdFromPath = pathMatch[1];
                }
                
                const finalAssetId = assetId || assetIdFromPath;
                
                // If we have an asset ID, check if it exists locally before allowing API call
                if (finalAssetId) {
                  // Check if we already have a cached result for this asset
                  const cacheKey = 'quixel_asset_' + finalAssetId;
                  const cachedResult = window[cacheKey];
                  
                  if (cachedResult !== undefined) {
                    // We have a cached result
                    if (cachedResult && cachedResult.path) {
                      // Asset exists locally! Prevent API call and import directly
                      e.preventDefault();
                      e.stopPropagation();
                      e.stopImmediatePropagation();
                      
                      // Change button text to "Importing"
                      if (btn._textElement) {
                        btn._textElement.textContent = 'Importing';
                        btn._textElement.classList.add('animated-dots');
                      }
                      
                      // Add progress bar
                      addProgressBarToButton(btn);
                      window.currentDownloadButton = btn;
                      
                      // Trigger import directly
                      console.log('QUIXEL_IMPORT_EXISTING_ASSET:' + cachedResult.path);
                      return; // Exit early, don't allow normal flow
                    } else {
                      // Asset doesn't exist, allow normal flow
                      // Don't prevent default, let it continue
                    }
                  } else {
                    // No cached result - prevent default while we check
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                    
                    // Request check from Electron
                    window.quixelAssetCheckInProgress = true;
                    window.quixelAssetExists = false;
                    window.quixelAssetPath = null;
                    console.log('QUIXEL_CHECK_ASSET_EXISTS:' + finalAssetId);
                    
                    // Wait for Electron to respond (it will set window.quixelAssetExists)
                    const checkInterval = setInterval(() => {
                      if (!window.quixelAssetCheckInProgress) {
                        clearInterval(checkInterval);
                        
                        // Cache the result
                        const result = window.quixelAssetExists ? { path: window.quixelAssetPath } : false;
                        window[cacheKey] = result;
                        
                        if (window.quixelAssetExists && window.quixelAssetPath) {
                          // Asset exists locally! Import directly
                          if (btn._textElement) {
                            btn._textElement.textContent = 'Importing';
                            btn._textElement.classList.add('animated-dots');
                          }
                          
                          addProgressBarToButton(btn);
                          window.currentDownloadButton = btn;
                          
                          // Trigger import
                          console.log('QUIXEL_IMPORT_EXISTING_ASSET:' + window.quixelAssetPath);
                        } else {
                          // Asset doesn't exist, manually trigger the button click to allow normal flow
                          // Create a synthetic click event that will bubble normally
                          const syntheticEvent = new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                          });
                          // Remove our handler temporarily, dispatch event, then re-add
                          const clickHandler = btn._quixelClickHandler;
                          if (clickHandler) {
                            btn.removeEventListener('click', clickHandler, true);
                            btn.dispatchEvent(syntheticEvent);
                            // Re-add handler after a short delay
                            setTimeout(() => {
                              btn.addEventListener('click', clickHandler, true);
                            }, 100);
                          }
                        }
                      }
                    }, 10); // Check every 10ms
                    
                    // Timeout after 200ms - if no response, assume asset doesn't exist
                    setTimeout(() => {
                      if (window.quixelAssetCheckInProgress) {
                        clearInterval(checkInterval);
                        window.quixelAssetCheckInProgress = false;
                        window[cacheKey] = false;
                        
                        // Manually trigger click to allow normal flow
                        const clickHandler = btn._quixelClickHandler;
                        if (clickHandler) {
                          const syntheticEvent = new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                          });
                          btn.removeEventListener('click', clickHandler, true);
                          btn.dispatchEvent(syntheticEvent);
                          setTimeout(() => {
                            btn.addEventListener('click', clickHandler, true);
                          }, 100);
                        }
                      }
                    }, 200);
                    
                    return; // Exit early while checking
                  }
                }

                // Normal flow: Change button text to "Downloading" with animated dots
                if (btn._textElement) {
                  btn._textElement.textContent = 'Downloading';
                  btn._textElement.classList.add('animated-dots');
                }

                // Add progress bar to button (will be updated by main process callbacks)
                setTimeout(() => {
                  addProgressBarToButton(btn);

                  // Store reference to this button for progress updates
                  window.currentDownloadButton = btn;

                  // Track download attempt start time for timeout mechanism
                  window.downloadAttemptStartTime = Date.now();

                  // Notify main process that download attempt started (via console message)
                  console.log('QUIXEL_DOWNLOAD_ATTEMPT_START:' + window.downloadAttemptStartTime);

                  // Set up timeout - if no download starts within 10 seconds, trigger failure
                  if (window.downloadTimeoutId) {
                    clearTimeout(window.downloadTimeoutId);
                  }

                  window.downloadTimeoutId = setTimeout(() => {
                    // Check if download actually started (will be cleared by onDownloadProgress/onDownloadComplete)
                    if (window.currentDownloadButton === btn && window.downloadAttemptStartTime) {
                      const timeSinceAttempt = Date.now() - window.downloadAttemptStartTime;
                      if (timeSinceAttempt >= 10000) {
                        // Timeout reached - no download started
                        // Trigger failure handler
                        if (window.onDownloadFailed) {
                          window.onDownloadFailed({
                            url: window.location.href,
                            error: 'Download timeout: No download started. The server may be experiencing issues or the request was invalid.'
                          });
                        }

                        // Reset button state
                        if (btn._textElement) {
                          btn._textElement.textContent = 'Import to Blender';
                          btn._textElement.classList.remove('animated-dots');
                        }

                        // Remove progress bar
                        const progressContainer = btn.querySelector('.quixel-linear-progress-container');
                        if (progressContainer) {
                          progressContainer.remove();
                        }

                        // Reset tracking
                        window.downloadAttemptStartTime = null;
                        window.downloadTimeoutId = null;
                        window.currentDownloadButton = null;
                      }
                    }
                  }, 10000); // 10 second timeout
                }, 100);
              };
              
              // Store handler reference on button for later removal
              btn._quixelClickHandler = clickHandler;
              btn.addEventListener('click', clickHandler, true); // Use capture phase
            }
          });
        }

        return foundButtons;
      };

      // Monitor URL changes for asset details
      let lastUrl = window.location.href;
      const urlObserver = new MutationObserver(() => {
        if (lastUrl !== window.location.href) {
          lastUrl = window.location.href;

          // Check if asset detail opened
          const urlParams = new URLSearchParams(window.location.search);
          const assetId = urlParams.get('assetId');
          if (assetId) {
            // Search immediately, then again after longer delay to ensure React has finished rendering
            findDownloadButton(true);
            setTimeout(() => findDownloadButton(), 500);
          }
        }
      });

      urlObserver.observe(document.body, {
        childList: true,
        subtree: true
      });


      // Monitor DOM changes to detect new download buttons (silent)
      const domObserver = new MutationObserver((mutations) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
          let shouldSearch = false;

          mutations.forEach(mutation => {
            if (mutation.addedNodes.length > 0) {
              mutation.addedNodes.forEach(node => {
                if (node.nodeType === 1) {
                  const isDownloadButton = node.matches && (
                    node.matches('button') || node.matches('a') || node.matches('[role="button"]')
                  ) && node.textContent.toLowerCase().includes('download');

                  const isModal = node.matches && (
                    node.matches('[role="dialog"]') || node.matches('[class*="modal"]') || node.matches('[class*="popup"]')
                  );

                  if (isModal || isDownloadButton) {
                    shouldSearch = true;
                  }
                }
              });
            }
          });

          if (shouldSearch) {
            findDownloadButton();
          }
        }, 200); // Increased from 100ms to 200ms to reduce processing during rapid DOM changes
      });

      domObserver.observe(document.body, {
        childList: true,
        subtree: true
      });

      // Function to inject custom download path settings
      function injectDownloadPathSettings() {
        // Check if already injected
        if (document.getElementById('quixel-portal-path-settings-wrapper')) {
          return;
        }

        // Find the Model Settings container (container___3YaWn container-large___Lz64p)
        const modelSettingsContainer = document.querySelector('div.container___3YaWn.container-large___Lz64p');
        if (!modelSettingsContainer) {
          return; // Container doesn't exist yet
        }

        // Get default download path - try localStorage first, then use default
        const savedPath = localStorage.getItem('quixelDownloadPath');
        const defaultPath = savedPath || window.quixelDownloadPath || 'C:\\\\Users\\\\User\\\\Documents\\\\Quixel Portal';

        // Create custom settings section HTML with header
        const pathSettingsHTML = \`
          <div id="quixel-portal-path-settings-wrapper">
            <!-- Header matching Model Settings style -->
            <div class="content___1WFTo tab-header___36tMb" style="margin-bottom: 16px;">
              <div class="heading___gFcc4">Download Settings</div>
            </div>

            <!-- Path input row -->
            <div class="subContainer___2ALnu" style="margin-right: 16px; padding-left: 24px; padding-right: 24px;">
              <div class="left___2S9Lx">
                <span class="label___2h7yz">Download Path</span>
              </div>
              <div class="right___38KOV" style="position: relative; flex: 1;">
                <input
                  id="quixel-download-path-input"
                  type="text"
                  value="\${defaultPath}"
                  style="
                    width: 100%;
                    height: 32px;
                    background: #1a1a1a;
                    border: 1px solid transparent;
                    border-radius: 4px;
                    padding: 0 40px 0 12px;
                    color: white;
                    font-family: inherit;
                    font-size: 13px;
                    outline: none;
                    box-sizing: border-box;
                    transition: border-color 0.2s;
                  "
                  placeholder="Choose download location..."
                  onfocus="this.style.borderColor='rgba(255, 255, 255, 0.2)'"
                  onblur="this.style.borderColor='transparent'"
                />
                <div
                  id="quixel-browse-path-btn"
                  style="
                    position: absolute;
                    right: 8px;
                    top: 50%;
                    transform: translateY(-50%);
                    cursor: pointer;
                    width: 24px;
                    height: 24px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    opacity: 0.7;
                    transition: opacity 0.2s;
                  "
                  onmouseover="this.style.opacity='1'"
                  onmouseout="this.style.opacity='0.7'"
                >
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M10 4H4C2.89543 4 2 4.89543 2 6V18C2 19.1046 2.89543 20 4 20H20C21.1046 20 22 19.1046 22 18V8C22 6.89543 21.1046 6 20 6H12L10 4Z" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                </div>
              </div>
            </div>
          </div>
        \`;

        // Insert at the beginning of the Model Settings container
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = pathSettingsHTML;
        const pathSettings = tempDiv.firstElementChild;

        modelSettingsContainer.insertBefore(pathSettings, modelSettingsContainer.firstChild);

        // Add event listeners
        const browseBtn = document.getElementById('quixel-browse-path-btn');
        const pathInput = document.getElementById('quixel-download-path-input');

        if (browseBtn && pathInput) {
          browseBtn.addEventListener('click', async () => {
            // Use the electron bridge to select path (shows prompt dialog)
            if (window.electronBridge && window.electronBridge.selectDownloadPath) {
              const selectedPath = await window.electronBridge.selectDownloadPath();
              if (selectedPath) {
                pathInput.value = selectedPath;
                window.quixelDownloadPath = selectedPath;
                localStorage.setItem('quixelDownloadPath', selectedPath);
              }
            }
          });

          // Save path when input changes
          pathInput.addEventListener('change', () => {
            window.quixelDownloadPath = pathInput.value;
            localStorage.setItem('quixelDownloadPath', pathInput.value);
          });

          // Load saved path from localStorage
          const savedPath = localStorage.getItem('quixelDownloadPath');
          if (savedPath) {
            pathInput.value = savedPath;
            window.quixelDownloadPath = savedPath;
          }
        }
      }

      // Monitor for settings dialog opening
      const settingsObserver = new MutationObserver(() => {
        injectDownloadPathSettings();
      });

      settingsObserver.observe(document.body, {
        childList: true,
        subtree: true
      });

      // Try to inject immediately if settings are already open
      injectDownloadPathSettings();

      // Create notification element if it doesn't exist
      function ensureNotificationElement() {
        let notification = document.getElementById('quixel-download-notification');
        if (!notification) {
          notification = document.createElement('div');
          notification.id = 'quixel-download-notification';
          document.body.appendChild(notification);
        }
        return notification;
      }

      // Function to show download completion notification
      function showDownloadNotification(downloadPath) {
        const notification = ensureNotificationElement();
        
        // Format the path for display (show only the relevant part)
        const pathParts = downloadPath.split(/[\\\\/]/);
        const displayPath = pathParts.length > 3 
          ? '...' + pathParts.slice(-3).join(' / ')
          : downloadPath;

        notification.innerHTML = \`
          <div class="notification-title">Download Completed</div>
          <div class="notification-message">Your download has been saved and extracted.</div>
          <div class="notification-path" data-path="\${downloadPath.replace(/\\\\/g, '\\\\\\\\')}">\${displayPath}</div>
        \`;

        // Add click handler to open file explorer
        const pathElement = notification.querySelector('.notification-path');
        pathElement.addEventListener('click', () => {
          // Use electronBridge to open file explorer
          if (window.electronBridge && window.electronBridge.openFileExplorer) {
            window.electronBridge.openFileExplorer(downloadPath);
          }
        });

        // Show notification
        setTimeout(() => {
          notification.classList.add('show');
        }, 10);

        // Auto-hide after 5 seconds
        setTimeout(() => {
          notification.classList.remove('show');
          setTimeout(() => {
            notification.innerHTML = '';
          }, 300); // Wait for fade-out animation
        }, 5000);
      }

      // Function to hide notification
      function hideNotification(notification) {
        notification.classList.remove('show');
        setTimeout(() => {
          notification.innerHTML = '';
        }, 300); // Wait for fade-out animation
      }

      // Function to show import to Blender notification
      function showImportNotification(completionData) {
        const notification = ensureNotificationElement();

        const assetName = completionData.asset_name || 'Asset';
        const thumbnailHtml = completionData.thumbnailDataUrl
          ? \`<img src="\${completionData.thumbnailDataUrl}" class="notification-thumbnail" />\`
          : '<div class="notification-thumbnail-placeholder">No preview</div>';

        notification.innerHTML = \`
          <button class="notification-close" title="Close"></button>
          <div class="notification-content-with-thumb">
            \${thumbnailHtml}
            <div class="notification-text">
              <div class="notification-title">Import Complete</div>
              <div class="notification-message">\${assetName} got imported in Blender</div>
            </div>
          </div>
        \`;

        // Show notification
        setTimeout(() => {
          notification.classList.add('show');
        }, 10);

        // Auto-hide after 5 seconds (only if still showing)
        let autoHideTimeout = setTimeout(() => {
          if (notification.classList.contains('show')) {
            hideNotification(notification);
          }
        }, 5000);
        
        // Add click handler for close button
        const closeBtn = notification.querySelector('.notification-close');
        if (closeBtn) {
          closeBtn.addEventListener('click', () => {
            clearTimeout(autoHideTimeout);
            hideNotification(notification);
          });
        }
      }

      // Listen for Blender import completion (set up via window object)
      window.onBlenderImportComplete = function(completionData) {
        // Restore button text to original
        if (window.currentDownloadButton) {
          removeProgressBar(window.currentDownloadButton);

          if (window.currentDownloadButton._textElement && window.currentDownloadButton.dataset.originalText) {
            window.currentDownloadButton._textElement.textContent = window.currentDownloadButton.dataset.originalText;
            window.currentDownloadButton._textElement.classList.remove('animated-dots');
          }

          window.currentDownloadButton = null;
        }

        // Show import complete notification with thumbnail
        showImportNotification(completionData);
      };

      // Set up download callbacks from main process
      window.onDownloadProgress = function(data) {
        // Clear timeout since download has started
        if (window.downloadTimeoutId) {
          clearTimeout(window.downloadTimeoutId);
          window.downloadTimeoutId = null;
        }
        window.downloadAttemptStartTime = null;
        
        if (window.currentDownloadButton) {
          updateProgressBar(window.currentDownloadButton, data.progress);
        }
      };

      window.onDownloadComplete = function(data) {
        // Clear timeout since download completed
        if (window.downloadTimeoutId) {
          clearTimeout(window.downloadTimeoutId);
          window.downloadTimeoutId = null;
        }
        window.downloadAttemptStartTime = null;
        
        if (window.currentDownloadButton) {
          updateProgressBar(window.currentDownloadButton, 100);

          // Change button text to "Importing" with animated dots
          if (window.currentDownloadButton._textElement) {
            window.currentDownloadButton._textElement.textContent = 'Importing';
            window.currentDownloadButton._textElement.classList.add('animated-dots');
          }

          // Don't auto-restore or show notification yet
          // Wait for Blender to send completion callback
        }

        // Don't show download complete notification - only show when import is done
      };

      window.onDownloadFailed = function(data) {
        // Clear timeout
        if (window.downloadTimeoutId) {
          clearTimeout(window.downloadTimeoutId);
          window.downloadTimeoutId = null;
        }
        window.downloadAttemptStartTime = null;
        
        if (window.currentDownloadButton) {
          removeProgressBar(window.currentDownloadButton);

          // Restore button text to original
          if (window.currentDownloadButton._textElement && window.currentDownloadButton.dataset.originalText) {
            window.currentDownloadButton._textElement.textContent = window.currentDownloadButton.dataset.originalText;
            window.currentDownloadButton._textElement.classList.remove('animated-dots');
          }

          window.currentDownloadButton = null;
        }

        alert('Download failed: ' + (data.error || 'Unknown error'));
      };
    })();
  `;

  browserView.webContents.executeJavaScript(debugScript);
}

// Element Inspector - Click on any element to get detailed info
function enableElementInspector() {
  if (!browserView) return;

  const inspectorScript = `
    (function() {
      // Remove existing inspector if active
      if (window.elementInspectorActive) {
        document.removeEventListener('click', window.elementInspectorHandler, true);
        document.removeEventListener('mouseover', window.elementInspectorHoverHandler, true);
        document.removeEventListener('mouseout', window.elementInspectorMouseoutHandler, true);

        // Remove any existing outlines
        document.querySelectorAll('[data-inspector-outline]').forEach(el => {
          el.style.outline = '';
          el.removeAttribute('data-inspector-outline');
        });

        window.elementInspectorActive = false;
        return;
      }

      window.elementInspectorActive = true;

      // Hover handler - highlight elements
      window.elementInspectorHoverHandler = function(e) {
        e.target.style.outline = '2px solid #ff6600';
        e.target.setAttribute('data-inspector-outline', 'true');
      };

      // Mouseout handler - remove highlight
      window.elementInspectorMouseoutHandler = function(e) {
        if (e.target.hasAttribute('data-inspector-outline')) {
          e.target.style.outline = '';
          e.target.removeAttribute('data-inspector-outline');
        }
      };

      // Click handler - inspect element
      window.elementInspectorHandler = function(e) {
        e.preventDefault();
        e.stopPropagation();

        const element = e.target;

        // Get comprehensive element info
        const info = {
          tagName: element.tagName,
          id: element.id || '(none)',
          className: element.className || '(none)',
          textContent: element.textContent.trim().substring(0, 100),
          attributes: {},
          computedStyles: {},
          position: element.getBoundingClientRect(),
          innerHTML: element.innerHTML.substring(0, 200)
        };

        // Get all attributes
        Array.from(element.attributes).forEach(attr => {
          info.attributes[attr.name] = attr.value;
        });

        // Get computed styles (most useful ones)
        const computed = window.getComputedStyle(element);
        const importantStyles = [
          'display', 'position', 'width', 'height',
          'background', 'background-color', 'color',
          'border', 'padding', 'margin',
          'font-family', 'font-size', 'font-weight',
          'z-index', 'opacity', 'cursor'
        ];
        importantStyles.forEach(style => {
          info.computedStyles[style] = computed[style];
        });

        // Generate CSS selector
        let selector = element.tagName.toLowerCase();
        if (element.id) {
          selector = '#' + element.id;
        } else if (element.className) {
          const classes = element.className.split(' ').filter(c => c.trim());
          if (classes.length > 0) {
            selector += '.' + classes.join('.');
          }
        }

        // Flash the element
        const originalOutline = element.style.outline;
        element.style.outline = '3px solid #00ff00';
        setTimeout(() => {
          element.style.outline = originalOutline;
        }, 1000);
      };

      // Add event listeners
      document.addEventListener('click', window.elementInspectorHandler, true);
      document.addEventListener('mouseover', window.elementInspectorHoverHandler, true);
      document.addEventListener('mouseout', window.elementInspectorMouseoutHandler, true);
    })();
  `;

  browserView.webContents.executeJavaScript(inspectorScript);
}

// ═══════════════════════════════════════════════════════════════
// 🖼️ THUMBNAIL CACHE - Create and manage cached thumbnails
// ═══════════════════════════════════════════════════════════════

function createCachedThumbnail(originalThumbPath, assetId) {
  try {
    if (!originalThumbPath || !fs.existsSync(originalThumbPath)) {
      return null;
    }

    // Create cache directory if it doesn't exist
    const userDataPath = app.getPath('userData');
    const cacheDir = path.join(userDataPath, 'thumbnail_cache');
    if (!fs.existsSync(cacheDir)) {
      fs.mkdirSync(cacheDir, { recursive: true });
    }

    // Generate cache filename based on asset ID
    const ext = path.extname(originalThumbPath);
    const cacheFilename = `${assetId}${ext}`;
    const cachePath = path.join(cacheDir, cacheFilename);

    // If cache already exists, return it
    if (fs.existsSync(cachePath)) {
      return cachePath;
    }

    // Load original image
    const originalImage = nativeImage.createFromPath(originalThumbPath);
    if (originalImage.isEmpty()) {
      return null;
    }

    // Resize to 64x64 thumbnail
    const resized = originalImage.resize({ width: 64, height: 64, quality: 'good' });

    // Save as PNG for consistent format and transparency support
    const pngBuffer = resized.toPNG();
    const pngCachePath = path.join(cacheDir, `${assetId}.png`);
    fs.writeFileSync(pngCachePath, pngBuffer);

    return pngCachePath;

  } catch (error) {
    return null;
  }
}

// ═══════════════════════════════════════════════════════════════
// 📥 IMPORT HISTORY - Save import events to history
// ═══════════════════════════════════════════════════════════════

function saveImportToHistory(importData) {
  try {
    const userDataPath = app.getPath('userData');
    const historyFile = path.join(userDataPath, 'import_history.json');

    // Read existing history or create new
    let history = { imports: [] };
    if (fs.existsSync(historyFile)) {
      try {
        const content = fs.readFileSync(historyFile, 'utf8');
        history = JSON.parse(content);
      } catch (err) {
        // If parsing fails, start with empty history
      }
    }

    // Re-read asset metadata to ensure we have the correct type
    let assetName = importData.asset_name || path.basename(importData.asset_path);
    let assetType = importData.asset_type || 'unknown';
    let assetId = path.basename(importData.asset_path);

    // Try to read from JSON file in the asset directory
    if (fs.existsSync(importData.asset_path)) {
      try {
        const files = fs.readdirSync(importData.asset_path);
        const jsonFile = files.find(f => f.endsWith('.json'));

        if (jsonFile) {
          const jsonPath = path.join(importData.asset_path, jsonFile);
          const metadata = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));

          // Extract asset information (same as download history)
          assetName = metadata.semanticTags?.name || metadata.name || assetName;
          assetType = metadata.semanticTags?.asset_type || metadata.type || assetType;
          assetId = metadata.id || assetId;
        }
      } catch (err) {
        // Failed to read metadata, use defaults
      }
    }

    // Create cached thumbnail (64px version)
    let cachedThumbnail = null;
    if (importData.thumbnail) {
      cachedThumbnail = createCachedThumbnail(importData.thumbnail, assetId);
    }

    // Create new import entry
    const importEntry = {
      id: `import-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      assetId: assetId,
      assetName: assetName,
      assetType: assetType,
      assetPath: importData.asset_path,
      thumbnail: importData.thumbnail,
      cachedThumbnail: cachedThumbnail, // Cached 64px version
      importTimestamp: Date.now(),
      importDate: new Date().toISOString()
    };

    // Add to beginning of array (most recent first)
    history.imports.unshift(importEntry);

    // Keep only last 1000 imports to prevent file from growing too large
    if (history.imports.length > 1000) {
      history.imports = history.imports.slice(0, 1000);
    }

    // Write back to file
    fs.writeFileSync(historyFile, JSON.stringify(history, null, 2));

  } catch (error) {
    // Failed to save import to history - don't crash
  }
}

// ═══════════════════════════════════════════════════════════════
// 📁 ASSET FOLDER VALIDATION - Check if folder contains valid files
// ═══════════════════════════════════════════════════════════════

function isAssetFolderValid(folderPath) {
  /**Check if an asset folder exists and contains valid files (FBX or surface materials).
  
  Args:
    folderPath: Path to the asset folder
    
  Returns:
    Object with {valid: boolean, isEmpty: boolean, reason: string}
  */
  try {
    if (!fs.existsSync(folderPath)) {
      return { valid: false, isEmpty: false, reason: 'Folder does not exist' };
    }
    
    const stats = fs.statSync(folderPath);
    if (!stats.isDirectory()) {
      return { valid: false, isEmpty: false, reason: 'Path is not a directory' };
    }
    
    // Read directory contents
    const files = fs.readdirSync(folderPath);
    
    // Check if folder is completely empty
    if (files.length === 0) {
      return { valid: false, isEmpty: true, reason: 'Folder is empty' };
    }
    
    // Check for FBX files (recursively)
    function findFBXFiles(dir) {
      let fbxFiles = [];
      try {
        const entries = fs.readdirSync(dir, { withFileTypes: true });
        for (const entry of entries) {
          const fullPath = path.join(dir, entry.name);
          if (entry.isDirectory()) {
            fbxFiles = fbxFiles.concat(findFBXFiles(fullPath));
          } else if (entry.name.toLowerCase().endsWith('.fbx')) {
            fbxFiles.push(fullPath);
          }
        }
      } catch (err) {
        // Ignore read errors
      }
      return fbxFiles;
    }
    
    const fbxFiles = findFBXFiles(folderPath);
    if (fbxFiles.length > 0) {
      return { valid: true, isEmpty: false, reason: `Found ${fbxFiles.length} FBX file(s)` };
    }
    
    // Check for surface material (JSON + texture files)
    const jsonFile = files.find(f => f.toLowerCase().endsWith('.json'));
    if (jsonFile) {
      // Check for texture files recursively (common texture extensions)
      function findTextureFiles(dir) {
        let textureFiles = [];
        try {
          const entries = fs.readdirSync(dir, { withFileTypes: true });
          for (const entry of entries) {
            const fullPath = path.join(dir, entry.name);
            if (entry.isDirectory()) {
              textureFiles = textureFiles.concat(findTextureFiles(fullPath));
            } else {
              const ext = path.extname(entry.name).toLowerCase();
              const textureExtensions = ['.png', '.jpg', '.jpeg', '.tga', '.tiff', '.tif', '.exr', '.hdr'];
              if (textureExtensions.includes(ext)) {
                textureFiles.push(fullPath);
              }
            }
          }
        } catch (err) {
          // Ignore read errors
        }
        return textureFiles;
      }
      
      const textureFiles = findTextureFiles(folderPath);
      if (textureFiles.length > 0) {
        return { valid: true, isEmpty: false, reason: `Found surface material (JSON + ${textureFiles.length} texture file(s))` };
      } else {
        return { valid: false, isEmpty: false, reason: 'Found JSON but no texture files' };
      }
    }
    
    // Folder exists but contains neither FBX files nor surface materials
    return { valid: false, isEmpty: false, reason: 'Folder exists but contains no FBX files or surface materials' };
    
  } catch (error) {
    return { valid: false, isEmpty: false, reason: `Error checking folder: ${error.message}` };
  }
}

// ═══════════════════════════════════════════════════════════════
// 📥 BLENDER IMPORT - Send import request to Blender
// ═══════════════════════════════════════════════════════════════

function sendImportRequestToBlender(assetPath) {
  try {
    // ═══════════════════════════════════════════════════════════════
    // 🔒 INSTANCE ID - Optional for single Blender instance setups
    // ═══════════════════════════════════════════════════════════════

    if (!blenderInstanceId) {
      console.warn('⚠️ Quixel Portal: No Blender instance ID provided');
      console.warn('   Running in backward compatibility mode (single instance)');
      console.warn('   Import request will be sent to any available Blender instance.');
    }

    const tmpDir = path.join(os.tmpdir(), 'quixel_portal');
    const requestFile = path.join(tmpDir, 'import_request.json');

    // Create temp directory if it doesn't exist
    if (!fs.existsSync(tmpDir)) {
      fs.mkdirSync(tmpDir, { recursive: true });
    }

    // Find thumbnail in the asset directory
    let thumbnailPath = null;
    if (fs.existsSync(assetPath)) {
      const files = fs.readdirSync(assetPath);

      // Look for preview images - prioritize common image formats
      const previewFile = files.find(f => {
        const lowerName = f.toLowerCase();
        return (lowerName.includes('_preview') || lowerName.includes('preview')) &&
               (lowerName.endsWith('.png') || lowerName.endsWith('.jpg') ||
                lowerName.endsWith('.jpeg') || lowerName.endsWith('.tga') ||
                lowerName.endsWith('.bmp'));
      }) || files.find(f => {
        // Fallback: any file with 'preview' in name (even without standard image extension)
        const lowerName = f.toLowerCase();
        return lowerName.includes('_preview') || lowerName.includes('preview');
      });

      if (previewFile) {
        thumbnailPath = path.join(assetPath, previewFile);
      }
    }

    // Get asset name and type from JSON
    let assetName = path.basename(assetPath);
    let assetType = 'unknown';
    const jsonFile = fs.existsSync(assetPath) ?
      fs.readdirSync(assetPath).find(f => f.endsWith('.json')) : null;
    if (jsonFile) {
      try {
        const jsonPath = path.join(assetPath, jsonFile);
        const metadata = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
        assetName = metadata.semanticTags?.name || metadata.name || assetName;
        assetType = metadata.semanticTags?.asset_type || metadata.type || 'unknown';
      } catch (err) {
        // Failed to read asset metadata from JSON
      }
    }

    // Write import request with thumbnail, name, type, and Blender instance ID
    const requestData = {
      asset_path: assetPath,
      thumbnail: thumbnailPath,
      asset_name: assetName,
      asset_type: assetType,
      blender_instance_id: blenderInstanceId, // Add instance ID to target specific Blender instance
      timestamp: Date.now()
    };

    fs.writeFileSync(requestFile, JSON.stringify(requestData, null, 2));

    console.log(`📤 Quixel Portal: Sent import request to Blender instance ${blenderInstanceId || '(any)'}`);

    // Start watching for completion
    watchForImportCompletion(assetPath);

  } catch (error) {
    // Failed to send import request to Blender
  }
}

// ═══════════════════════════════════════════════════════════════
// 💓 HEARTBEAT MONITORING - Check if Blender is still alive
// ═══════════════════════════════════════════════════════════════

function checkBlenderHeartbeat(instanceId) {
  try {
    const tmpDir = path.join(os.tmpdir(), 'quixel_portal');
    const heartbeatFile = path.join(tmpDir, `heartbeat_${instanceId}.txt`);

    // Check if heartbeat file exists
    if (!fs.existsSync(heartbeatFile)) {
      console.log('⚠️ Quixel Portal: Heartbeat file not found (might be in grace period)');
      return;
    }

    // Read heartbeat file
    const heartbeatData = JSON.parse(fs.readFileSync(heartbeatFile, 'utf8'));
    const timestamp = heartbeatData.timestamp;
    const currentTime = Date.now() / 1000;  // Convert to seconds
    const age = currentTime - timestamp;

    console.log(`💓 Quixel Portal: Heartbeat check - Blender last seen ${age.toFixed(0)} seconds ago`);

    // If heartbeat is older than 90 seconds, Blender is dead
    if (age > 90) {
      console.log('⚠️ Quixel Portal: Heartbeat EXPIRED - Blender last seen ' + age.toFixed(0) + ' seconds ago');
      console.log('🛑 Quixel Portal: Closing Electron (Blender instance closed)');

      // Close Electron gracefully
      app.quit();
    }

  } catch (error) {
    console.log('⚠️ Quixel Portal: Failed to check heartbeat:', error.message);
    // Don't close on error - might be temporary file lock or parse error
  }
}

// Watch for Blender import completion
function watchForImportCompletion(assetPath) {
  const tmpDir = path.join(os.tmpdir(), 'quixel_portal');
  const completionFile = path.join(tmpDir, 'import_complete.json');

  const checkInterval = setInterval(() => {
    if (fs.existsSync(completionFile)) {
      try {
        // Read completion data
        const completionData = JSON.parse(fs.readFileSync(completionFile, 'utf8'));

        // Check if this completion is for our asset
        if (completionData.asset_path === assetPath) {
          // Convert thumbnail to base64 data URL if it exists
          if (completionData.thumbnail && fs.existsSync(completionData.thumbnail)) {
            try {
              const imageBuffer = fs.readFileSync(completionData.thumbnail);
              const ext = path.extname(completionData.thumbnail).toLowerCase();
              let mimeType = 'image/png';
              if (ext === '.jpg' || ext === '.jpeg') mimeType = 'image/jpeg';
              else if (ext === '.bmp') mimeType = 'image/bmp';
              else if (ext === '.tga') mimeType = 'image/tga';

              const base64 = imageBuffer.toString('base64');
              completionData.thumbnailDataUrl = `data:${mimeType};base64,${base64}`;
            } catch (err) {
              // Failed to convert thumbnail to base64
            }
          }

          // Save to import history
          saveImportToHistory(completionData);

          // Delete completion file
          fs.unlinkSync(completionFile);

          // Notify the renderer process (BrowserView)
          if (browserView) {
            browserView.webContents.executeJavaScript(
              `if (window.onBlenderImportComplete) {
                window.onBlenderImportComplete(${JSON.stringify(completionData)});
              }`
            );
          }

          console.log(`✅ Quixel Portal: Import completed for '${completionData.asset_name}'`);

          clearInterval(checkInterval);
        }
      } catch (error) {
        clearInterval(checkInterval);
      }
    }
  }, 500); // Check every 500ms

  // Stop checking after 30 seconds
  setTimeout(() => {
    clearInterval(checkInterval);
  }, 30000);
}

// ═══════════════════════════════════════════════════════════════
// 🎨 SPLASH SCREEN - Show beautiful loading screen
// ═══════════════════════════════════════════════════════════════

function createSplashScreen() {
  splashWindow = new BrowserWindow({
    width: 500,
    height: 600,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    center: true,
    resizable: false,
    skipTaskbar: true,
    icon: path.join(__dirname, 'assets', 'images', 'windows_icon.ico'),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true
    }
  });

  splashWindow.loadFile(path.join(__dirname, 'splash.html'));
}

function updateSplashStatus(message) {
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.webContents.send('loading-status', message);
  }
}

function closeSplashScreen() {
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.close();
    splashWindow = null;
  }
}

function createWindow() {
  // Create the browser window with custom frame (hidden initially)
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    frame: false, // Remove default frame
    titleBarStyle: 'hidden',
    show: false, // Start hidden - will show after splash closes
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      webviewTag: false
    },
    icon: path.join(__dirname, 'assets', 'images', 'windows_icon.ico')
  });

  // Set window title with instance ID for easy identification
  if (blenderInstanceId) {
    const shortId = blenderInstanceId.slice(-8);
    mainWindow.setTitle(`Quixel Portal (${shortId})`);
    console.log(`🪟 Quixel Portal: Window title set to "Quixel Portal (${shortId})"`);

    // Offset window position based on instance ID hash to prevent perfect overlap
    const hashCode = (str) => {
      let hash = 0;
      for (let i = 0; i < str.length; i++) {
        hash = ((hash << 5) - hash) + str.charCodeAt(i);
        hash = hash & hash; // Convert to 32bit integer
      }
      return Math.abs(hash);
    };

    const offset = hashCode(blenderInstanceId) % 5;
    const baseX = 100;
    const baseY = 100;
    mainWindow.setPosition(baseX + (offset * 40), baseY + (offset * 40));
    console.log(`🪟 Quixel Portal: Window position offset: ${offset * 40}px`);
  }

  // Show window once it's ready
  mainWindow.once('ready-to-show', () => {
    // Close splash screen with a smooth transition
    setTimeout(() => {
      closeSplashScreen();

      // Show main window after splash closes
      setTimeout(() => {
        mainWindow.show();
        mainWindow.focus();
      }, 200);
    }, 500);
  });

  // ═══════════════════════════════════════════════════════════════
  // 🚀 SOLUTION 1: HIDE INSTEAD OF CLOSE (Background Mode)
  // ═══════════════════════════════════════════════════════════════

  // Prevent window from closing - hide it instead
  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();

      // Flush session before hiding to ensure cookies are saved
      if (browserView && browserView.webContents.session) {
        browserView.webContents.session.flushStorageData();
      }

      mainWindow.hide();

      return false;
    }
  });

  // Load the custom titlebar HTML first
  mainWindow.loadFile(path.join(__dirname, 'titlebar.html'));

  // Create BrowserView for the website with persistent session
  const ses = session.fromPartition('persist:quixel');

  // ═══════════════════════════════════════════════════════════════
  // 🍪 COOKIE INTERCEPTOR - Convert session cookies to persistent
  // ═══════════════════════════════════════════════════════════════

  // Intercept cookies being set and make them persistent
  ses.cookies.addListener('changed', async (event, cookie, cause, removed) => {
    if (removed) return; // Don't care about removed cookies

    // Only process cookies from quixel.com and epicgames.com
    if (!cookie.domain.includes('quixel.com') && !cookie.domain.includes('epicgames.com')) {
      return;
    }

    // Check if this is a session cookie (no expiration date)
    if (!cookie.expirationDate || cookie.expirationDate === undefined) {
      // Convert session cookie to persistent cookie
      // Set expiration to 1 year from now
      const oneYearFromNow = Math.floor(Date.now() / 1000) + (365 * 24 * 60 * 60);

      const persistentCookie = {
        url: `https://${cookie.domain.replace(/^\./, '')}${cookie.path}`,
        name: cookie.name,
        value: cookie.value,
        domain: cookie.domain,
        path: cookie.path,
        secure: cookie.secure,
        httpOnly: cookie.httpOnly,
        expirationDate: oneYearFromNow, // 1 year from now
        sameSite: cookie.sameSite || 'no_restriction'
      };

      try {
        await ses.cookies.set(persistentCookie);

        // Flush immediately after converting
        ses.flushStorageData();
      } catch (error) {
        // Failed to convert cookie
      }
    } else {
      // Cookie already has expiration - just make sure it's saved

      // Flush to disk
      setTimeout(() => {
        ses.flushStorageData();
      }, 100);
    }
  });

  browserView = new BrowserView({
    webPreferences: {
      session: ses,
      nodeIntegration: false,
      contextIsolation: true
    }
  });

  // Set realistic Chrome user-agent to avoid Electron detection
  // This makes the app appear as a regular Chrome browser instead of Electron
  const chromeUserAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';
  browserView.webContents.setUserAgent(chromeUserAgent);

  mainWindow.setBrowserView(browserView);

  // Track downloads panel state
  let isDownloadsPanelOpen = false;
  const DOWNLOADS_PANEL_WIDTH = 330;

  // Set the bounds for the browser view (below the titlebar)
  const updateBounds = () => {
    // Use getContentBounds() for frameless windows to get accurate content area
    const bounds = mainWindow.getContentBounds();
    const panelWidth = isDownloadsPanelOpen ? DOWNLOADS_PANEL_WIDTH : 0;
    browserView.setBounds({
      x: 0,
      y: 40,
      width: bounds.width - panelWidth,
      height: bounds.height - 40
    });
  };

  updateBounds();
  mainWindow.on('resize', updateBounds);
  // Add small delay for fullscreen/maximize events to ensure bounds are updated
  mainWindow.on('enter-full-screen', () => setTimeout(updateBounds, 100));
  mainWindow.on('leave-full-screen', () => setTimeout(updateBounds, 100));
  mainWindow.on('maximize', () => setTimeout(updateBounds, 100));
  mainWindow.on('unmaximize', () => setTimeout(updateBounds, 100));

  // Function to update panel state and bounds
  global.setDownloadsPanelState = (isOpen) => {
    isDownloadsPanelOpen = isOpen;
    updateBounds();
  };

  // ═══════════════════════════════════════════════════════════════
  // 🚀 INSTANT AUTH CHECK: Check cookies BEFORE loading page
  // ═══════════════════════════════════════════════════════════════

  // Store sign-in URL (will be auto-detected or use fallback)
  let signInURL = null;

  // Flag to track if we're in initial auth check mode
  let isInitialAuthCheck = true;

  async function loadQuixelWithAuthCheck() {
    try {
      // Always load homepage regardless of authentication status
      // Let Quixel handle the login flow naturally without automatic redirection
      isInitialAuthCheck = false;
      browserView.webContents.loadURL('https://quixel.com/megascans/home');
    } catch (error) {
      isInitialAuthCheck = false;

      // Fallback: load homepage anyway
      browserView.webContents.loadURL('https://quixel.com/megascans/home');
    }
  }

  // Load Quixel website with authentication check
  loadQuixelWithAuthCheck();

  // ═══════════════════════════════════════════════════════════════
  // 🔒 CREATE LOCK FILE - Prevent multiple Electrons for same instance
  // ═══════════════════════════════════════════════════════════════

  if (blenderInstanceId) {
    try {
      const tmpDir = path.join(os.tmpdir(), 'quixel_portal');

      // Create temp directory if it doesn't exist
      if (!fs.existsSync(tmpDir)) {
        fs.mkdirSync(tmpDir, { recursive: true });
      }

      const lockFile = path.join(tmpDir, `electron_lock_${blenderInstanceId}.txt`);

      // Write lock file with PID and timestamp
      const lockData = {
        pid: process.pid,
        instance_id: blenderInstanceId,
        timestamp: Date.now()
      };

      fs.writeFileSync(lockFile, JSON.stringify(lockData, null, 2));
      console.log(`🔒 Quixel Portal: Lock file created - ${lockFile}`);

      // Update lock file periodically to keep it fresh (prevents stale file detection)
      const updateLockFile = () => {
        try {
          if (fs.existsSync(lockFile)) {
            const lockData = {
              pid: process.pid,
              instance_id: blenderInstanceId,
              timestamp: Date.now()
            };
            fs.writeFileSync(lockFile, JSON.stringify(lockData, null, 2));
          }
        } catch (error) {
          // Failed to update lock file, not critical
        }
      };

      // Update lock file every 30 seconds to keep it fresh
      setInterval(updateLockFile, 30000);

      // Delete lock file when Electron closes
      app.on('before-quit', () => {
        try {
          if (fs.existsSync(lockFile)) {
            fs.unlinkSync(lockFile);
            console.log('🔓 Quixel Portal: Lock file deleted');
          }
        } catch (error) {
          console.log('⚠️ Quixel Portal: Failed to delete lock file:', error.message);
        }
      });

    } catch (error) {
      console.log('⚠️ Quixel Portal: Failed to create lock file:', error.message);
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // 👁️ MONITOR FOR SHOW WINDOW SIGNAL
  // ═══════════════════════════════════════════════════════════════

  if (blenderInstanceId) {
    console.log('👁️ Quixel Portal: Starting show window signal monitoring');

    // Check for show window signal every 100ms for faster response
    setInterval(() => {
      try {
        const tmpDir = path.join(os.tmpdir(), 'quixel_portal');
        const signalFile = path.join(tmpDir, `show_window_${blenderInstanceId}.txt`);

        if (fs.existsSync(signalFile)) {
          console.log('👁️ Quixel Portal: Show window signal received!');

          // Show and focus the window, ensuring it comes to foreground
          if (mainWindow) {
            // Restore if minimized
            if (mainWindow.isMinimized()) {
              mainWindow.restore();
            }
            
            // Show if hidden
            if (!mainWindow.isVisible()) {
              mainWindow.show();
            }
            
            // Force window to foreground on Windows
            if (process.platform === 'win32') {
              // Temporarily set always on top to force window to foreground
              const wasAlwaysOnTop = mainWindow.isAlwaysOnTop();
              if (!wasAlwaysOnTop) {
                mainWindow.setAlwaysOnTop(true);
              }
              
              // Focus the window
              mainWindow.focus();
              
              // Restore always on top state after a brief moment
              if (!wasAlwaysOnTop) {
                setTimeout(() => {
                  mainWindow.setAlwaysOnTop(false);
                }, 100);
              }
            } else {
              // On other platforms, just focus
              mainWindow.focus();
            }
            
            // Move window to front (additional method for ensuring foreground)
            mainWindow.moveTop();
            
            console.log('🪟 Quixel Portal: Window restored, shown, and brought to foreground');
          }

          // Delete the signal file
          try {
            fs.unlinkSync(signalFile);
          } catch (error) {
            // Failed to delete signal file, not critical
          }
        }
      } catch (error) {
        // Error checking signal file, not critical
      }
    }, 100);  // Check every 100ms for faster response
  }

  // ═══════════════════════════════════════════════════════════════
  // 💓 START HEARTBEAT MONITORING
  // ═══════════════════════════════════════════════════════════════

  if (blenderInstanceId) {
    console.log(`💓 Quixel Portal: Starting heartbeat monitoring for instance ${blenderInstanceId}`);

    // Wait 45 seconds before starting checks (grace period for Blender to write first heartbeat)
    setTimeout(() => {
      console.log('💓 Quixel Portal: Heartbeat monitoring active (checking every 60 seconds)');

      // Check heartbeat every 60 seconds
      setInterval(() => {
        checkBlenderHeartbeat(blenderInstanceId);
      }, 60000);  // 60 seconds

      // Do first check immediately after grace period
      checkBlenderHeartbeat(blenderInstanceId);

    }, 45000);  // 45 second grace period
  } else {
    console.log('⚠️ Quixel Portal: No instance ID - heartbeat monitoring disabled');
  }

  // ═══════════════════════════════════════════════════════════════
  // 🌐 NETWORK REQUEST INTERCEPTION - Detect API errors
  // ═══════════════════════════════════════════════════════════════

  // Track download attempts to detect when API calls fail
  let downloadAttemptStartTime = null;
  let downloadTimeoutId = null;

  // Intercept failed network requests to detect API errors
  ses.webRequest.onCompleted(
    {
      urls: ['https://quixel.com/*', 'https://*.quixel.com/*', 'https://*.epicgames.com/*']
    },
    (details) => {
      // Check for error status codes (400, 401, 403, 404, 500, etc.)
      if (details.statusCode >= 400 && downloadAttemptStartTime !== null) {
        // Check if this error occurred within 10 seconds of a download attempt
        const timeSinceAttempt = Date.now() - downloadAttemptStartTime;
        if (timeSinceAttempt < 10000) {
          // This is likely an API error related to the download attempt
          // Clear the timeout since we detected the error
          if (downloadTimeoutId) {
            clearTimeout(downloadTimeoutId);
            downloadTimeoutId = null;
          }

          // Reset download attempt tracking
          downloadAttemptStartTime = null;

          // Notify the page about the failure
          if (browserView) {
            browserView.webContents.executeJavaScript(
              `if (window.onDownloadFailed) {
                window.onDownloadFailed({
                  url: '${details.url}',
                  error: 'API Error: Request failed with status code ${details.statusCode}'
                });
              }`
            );
          }
        }
      }
    }
  );

  // Also intercept response errors
  ses.webRequest.onErrorOccurred(
    {
      urls: ['https://quixel.com/*', 'https://*.quixel.com/*', 'https://*.epicgames.com/*']
    },
    (details) => {
      if (downloadAttemptStartTime !== null) {
        const timeSinceAttempt = Date.now() - downloadAttemptStartTime;
        if (timeSinceAttempt < 10000) {
          if (downloadTimeoutId) {
            clearTimeout(downloadTimeoutId);
            downloadTimeoutId = null;
          }

          downloadAttemptStartTime = null;

          if (browserView) {
            browserView.webContents.executeJavaScript(
              `if (window.onDownloadFailed) {
                window.onDownloadFailed({
                  url: '${details.url}',
                  error: 'Network Error: ${details.error}'
                });
              }`
            );
          }
        }
      }
    }
  );

  // Global download handler - intercepts ALL downloads from BrowserView
  ses.on('will-download', (event, item, webContents) => {
    // CRITICAL: Set save path IMMEDIATELY (synchronously) to prevent Windows file dialog
    // We must do this before any async operations, otherwise the dialog will appear
    const fs = require('fs');
    const defaultBasePath = path.join(os.homedir(), 'Documents', 'Quixel Portal');
    const defaultDownloadPath = path.join(defaultBasePath, 'Downloaded');
    
    // Create Downloaded directory if it doesn't exist
    if (!fs.existsSync(defaultDownloadPath)) {
      fs.mkdirSync(defaultDownloadPath, { recursive: true });
    }
    
    const defaultFullPath = path.join(defaultDownloadPath, item.getFilename());
    
    // Set save path immediately to prevent file dialog
    item.setSavePath(defaultFullPath);
    
    // Clear download timeout since download actually started
    if (downloadTimeoutId) {
      clearTimeout(downloadTimeoutId);
      downloadTimeoutId = null;
    }
    downloadAttemptStartTime = null;
    // Notify titlebar window that download started
    if (mainWindow) {
      mainWindow.webContents.send('download-started', {
        filename: item.getFilename(),
        url: item.getURL()
      });
    }

    // Get custom download path from the injected script via executeJavaScript
    // Note: We've already set a default path above to prevent the dialog
    // If a custom path is found, we'll use it for validation and folder operations
    browserView.webContents.executeJavaScript(
      'localStorage.getItem("quixelDownloadPath") || window.quixelDownloadPath || null'
    ).then(customPath => {
      const basePath = customPath || defaultBasePath;
      const downloadPath = path.join(basePath, 'Downloaded');
      
      // Create Downloaded directory if it doesn't exist (in case custom path is different)
      if (!fs.existsSync(downloadPath)) {
        fs.mkdirSync(downloadPath, { recursive: true });
      }

      // Determine the final path to use
      // If custom path exists, use it; otherwise use the default we already set
      const finalPath = customPath ? path.join(downloadPath, item.getFilename()) : defaultFullPath;
      
      // If we have a custom path and it's different from what we set, try to update it
      // Note: This might fail if download already started, but we've prevented the dialog
      if (customPath && finalPath !== defaultFullPath) {
        try {
          item.setSavePath(finalPath);
          console.log(`📁 Quixel Portal: Using custom download path: ${finalPath}`);
        } catch (err) {
          // If we can't change it (download already started), use the default path
          console.log(`⚠️ Quixel Portal: Could not update save path to custom location, using default: ${defaultFullPath}`);
        }
      }

      // Use the final path for all operations (validation, checking existence, etc.)
      const fullPath = finalPath;

      // Check if file already exists (for ZIP files, check if extracted folder exists and is valid)
      let alreadyExists = false;
      let existingPath = fullPath;
      let folderValidation = null;

      if (item.getFilename().endsWith('.zip')) {
        const zipFileName = path.basename(item.getFilename(), '.zip');
        const extractPath = path.join(downloadPath, zipFileName);
        if (fs.existsSync(extractPath)) {
          // Validate that the extracted folder contains valid files
          folderValidation = isAssetFolderValid(extractPath);
          if (folderValidation.valid) {
            alreadyExists = true;
            existingPath = extractPath;
          } else {
            // Folder exists but is empty or invalid - allow re-download
            console.log(`⚠️ Quixel Portal: Extracted folder exists but is invalid: ${folderValidation.reason}`);
            console.log(`   Allowing re-download to fix empty/invalid folder`);
            // Remove the empty/invalid folder to allow fresh extraction
            try {
              fs.rmSync(extractPath, { recursive: true, force: true });
              console.log(`🗑️ Quixel Portal: Removed invalid folder: ${extractPath}`);
            } catch (rmError) {
              console.log(`⚠️ Quixel Portal: Failed to remove invalid folder: ${rmError.message}`);
            }
          }
        }
      } else if (fs.existsSync(fullPath)) {
        // For non-ZIP files, check if it's a directory and validate it
        const stats = fs.statSync(fullPath);
        if (stats.isDirectory()) {
          folderValidation = isAssetFolderValid(fullPath);
          if (folderValidation.valid) {
            alreadyExists = true;
          } else {
            // Directory exists but is empty or invalid - allow re-download
            console.log(`⚠️ Quixel Portal: Asset folder exists but is invalid: ${folderValidation.reason}`);
            console.log(`   Allowing re-download to fix empty/invalid folder`);
            // Remove the empty/invalid folder to allow fresh download
            try {
              fs.rmSync(fullPath, { recursive: true, force: true });
              console.log(`🗑️ Quixel Portal: Removed invalid folder: ${fullPath}`);
            } catch (rmError) {
              console.log(`⚠️ Quixel Portal: Failed to remove invalid folder: ${rmError.message}`);
            }
          }
        } else {
          // It's a file, not a directory - assume it exists
          alreadyExists = true;
        }
      }

      // If asset already exists and is valid, skip download and notify
      if (alreadyExists) {

        // Set a save path to prevent the file dialog from appearing
        item.setSavePath(fullPath);

        // Cancel the download immediately
        item.cancel();

        // Send import request to Blender
        sendImportRequestToBlender(existingPath);

        // Notify the page immediately that the asset is ready
        browserView.webContents.executeJavaScript(
          `if (window.onDownloadComplete) {
            window.onDownloadComplete({
              url: '${item.getURL()}',
              path: '${existingPath.replace(/\\/g, '\\\\')}',
              extracted: true,
              alreadyExisted: true
            });
          }`
        );
        return;
      }

      item.setSavePath(fullPath);

      // Track progress
      item.on('updated', (event, state) => {
        if (state === 'progressing') {
          if (!item.isPaused()) {
            const progress = (item.getReceivedBytes() / item.getTotalBytes()) * 100;

            // Send progress back to the page
            browserView.webContents.executeJavaScript(
              `if (window.onDownloadProgress) {
                window.onDownloadProgress({
                  url: '${item.getURL()}',
                  progress: ${progress},
                  loaded: ${item.getReceivedBytes()},
                  total: ${item.getTotalBytes()}
                });
              }`
            );

            // Send progress to titlebar window (downloads panel)
            if (mainWindow) {
              mainWindow.webContents.send('download-progress-update', {
                filename: item.getFilename(),
                url: item.getURL(),
                progress: progress,
                loaded: item.getReceivedBytes(),
                total: item.getTotalBytes()
              });
            }
          }
        }
      });

      // Handle completion
      item.once('done', (event, state) => {
        if (state === 'completed') {
          // Unzip if it's a zip file
          if (fullPath.endsWith('.zip')) {

            // Extract to a folder with the same name as the zip (without .zip extension)
            const zipFileName = path.basename(fullPath, '.zip');
            const extractPath = path.join(path.dirname(fullPath), zipFileName);

            // Create extraction directory if it doesn't exist
            if (!fs.existsSync(extractPath)) {
              fs.mkdirSync(extractPath, { recursive: true });
            }

            // Use extract-zip for reliable extraction
            // extract-zip is required at top level, so it should be available here

            extractZip(fullPath, { dir: extractPath })
              .then(() => {
                // Delete the zip file after extraction
                try {
                  fs.unlinkSync(fullPath);
                } catch (err) {
                  // Failed to delete zip file
                }

                // Send import request to Blender
                sendImportRequestToBlender(extractPath);

                // Notify the page with extracted path
                browserView.webContents.executeJavaScript(
                  `if (window.onDownloadComplete) {
                    window.onDownloadComplete({
                      url: '${item.getURL()}',
                      path: '${extractPath.replace(/\\/g, '\\\\')}',
                      extracted: true
                    });
                  }`
                );

                // Notify titlebar window (downloads panel)
                if (mainWindow) {
                  mainWindow.webContents.send('download-completed', {
                    filename: item.getFilename(),
                    url: item.getURL(),
                    path: extractPath
                  });
                }
              })
              .catch((err) => {
                // Still notify with zip path if extraction fails
                browserView.webContents.executeJavaScript(
                  `if (window.onDownloadComplete) {
                    window.onDownloadComplete({
                      url: '${item.getURL()}',
                      path: '${fullPath.replace(/\\/g, '\\\\')}',
                      extracted: false,
                      error: 'Extraction failed: ' + err.message
                    });
                  }`
                );
              });
          } else {
            // Not a zip file
            // Send import request to Blender (use the parent directory)
            sendImportRequestToBlender(path.dirname(fullPath));

            // Notify the page
            browserView.webContents.executeJavaScript(
              `if (window.onDownloadComplete) {
                window.onDownloadComplete({
                  url: '${item.getURL()}',
                  path: '${fullPath.replace(/\\/g, '\\\\')}'
                });
              }`
            );

            // Notify titlebar window (downloads panel)
            if (mainWindow) {
              mainWindow.webContents.send('download-completed', {
                filename: item.getFilename(),
                url: item.getURL(),
                path: fullPath
              });
            }
          }
        } else if (state === 'interrupted') {
          // Download was interrupted
        } else if (state === 'cancelled') {
          // Download was cancelled
        } else {
          // Notify the page of failure
          browserView.webContents.executeJavaScript(
            `if (window.onDownloadFailed) {
              window.onDownloadFailed({
                url: '${item.getURL()}',
                error: '${state}'
              });
            }`
          );
        }
      });
    }).catch(err => {
      // Fallback to default path
      const defaultPath = path.join(os.homedir(), 'Documents', 'Quixel Portal');
      item.setSavePath(path.join(defaultPath, item.getFilename()));
    });
  });

  // Helper function to update navigation button states
  function updateNavigationButtonStates() {
    if (!browserView || !mainWindow) return;
    
    const currentURL = browserView.webContents.getURL();
    const canGoBack = browserView.webContents.canGoBack();
    const canGoForward = browserView.webContents.canGoForward();

    mainWindow.webContents.send('navigation-finished', {
      url: currentURL,
      canGoBack: canGoBack,
      canGoForward: canGoForward
    });
  }

  // Handle navigation events from BrowserView
  browserView.webContents.on('did-start-navigation', (event, url) => {
    // Auto-detect sign-in URL from navigation
    // Sign-in URLs typically contain 'login', 'signin', 'auth', or are Epic Games URLs
    if (url && (
      url.includes('/login') ||
      url.includes('/signin') ||
      url.includes('/auth') ||
      url.includes('epicgames.com')
    )) {
      // Only store if it's different from homepage
      if (!url.includes('/megascans/home')) {
        if (!signInURL || signInURL !== url) {
          signInURL = url;

          // Mark initial auth check as complete
          isInitialAuthCheck = false;
        }
      }
    }

    mainWindow.webContents.send('navigation-started', url);
  });

  // Handle full page navigations (not just in-page)
  browserView.webContents.on('did-navigate', (event, url) => {
    // Update navigation button states after navigation
    updateNavigationButtonStates();
  });

  browserView.webContents.on('did-finish-load', () => {
    // Update navigation button states
    updateNavigationButtonStates();

    // Flush session after page loads (cookies might have been set during navigation)
    if (browserView && browserView.webContents.session) {
      browserView.webContents.session.flushStorageData();
    }

    // Hide page during initial auth check to prevent flash
    if (isInitialAuthCheck) {
      browserView.webContents.insertCSS('body { opacity: 0 !important; }');
    }

    // Inject debug script when page loads
    injectDebugScript();
  });

  browserView.webContents.on('page-title-updated', (event, title) => {
    mainWindow.webContents.send('page-title-updated', title);
  });

  // Listen for console messages to handle file explorer requests AND sign-in URL detection
  browserView.webContents.on('console-message', (event, level, message, line, sourceId) => {
    // Check if asset exists locally before allowing API call
    if (typeof message === 'string' && message.startsWith('QUIXEL_CHECK_ASSET_EXISTS:')) {
      const assetId = message.substring('QUIXEL_CHECK_ASSET_EXISTS:'.length);
      
      // Get download path
      browserView.webContents.executeJavaScript(
        'localStorage.getItem("quixelDownloadPath") || window.quixelDownloadPath || null'
      ).then(customPath => {
        const basePath = customPath || path.join(os.homedir(), 'Documents', 'Quixel Portal');
        const downloadPath = path.join(basePath, 'Downloaded');
        
        // Check all folders in Downloaded directory for matching asset
        let foundAssetPath = null;
        
        if (fs.existsSync(downloadPath)) {
          try {
            const folders = fs.readdirSync(downloadPath);
            for (const folder of folders) {
              const folderPath = path.join(downloadPath, folder);
              if (!fs.statSync(folderPath).isDirectory()) continue;
              
              // Check if folder contains JSON with matching ID
              const files = fs.readdirSync(folderPath);
              const jsonFile = files.find(f => f.endsWith('.json'));
              
              if (jsonFile) {
                try {
                  const jsonPath = path.join(folderPath, jsonFile);
                  const metadata = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
                  const folderAssetId = metadata.id || folder;
                  
                  // Check if IDs match (exact match or folder name match)
                  if (folderAssetId === assetId || folder === assetId) {
                    // Validate that folder contains valid files
                    const validation = isAssetFolderValid(folderPath);
                    if (validation.valid) {
                      foundAssetPath = folderPath;
                      break;
                    }
                  }
                } catch (err) {
                  // Skip invalid JSON files
                }
              } else {
                // No JSON, check if folder name matches asset ID
                if (folder === assetId) {
                  const validation = isAssetFolderValid(folderPath);
                  if (validation.valid) {
                    foundAssetPath = folderPath;
                    break;
                  }
                }
              }
            }
          } catch (err) {
            // Error reading download directory
          }
        }
        
        // Respond to injected script with result
        if (foundAssetPath) {
          browserView.webContents.executeJavaScript(
            `window.quixelAssetExists = true; window.quixelAssetPath = ${JSON.stringify(foundAssetPath)}; window.quixelAssetCheckInProgress = false;`
          );
          console.log(`✅ Quixel Portal: Asset ${assetId} found locally at ${foundAssetPath}`);
        } else {
          browserView.webContents.executeJavaScript(
            `window.quixelAssetExists = false; window.quixelAssetPath = null; window.quixelAssetCheckInProgress = false;`
          );
        }
      });
      
      return; // Don't process further
    }
    
    // Handle import of existing asset (triggered when asset exists locally)
    if (typeof message === 'string' && message.startsWith('QUIXEL_IMPORT_EXISTING_ASSET:')) {
      const assetPath = message.substring('QUIXEL_IMPORT_EXISTING_ASSET:'.length);
      
      // Send import request to Blender
      sendImportRequestToBlender(assetPath);
      
      // Notify the page that import started
      browserView.webContents.executeJavaScript(
        `if (window.onDownloadComplete) {
          window.onDownloadComplete({
            url: window.location.href,
            path: ${JSON.stringify(assetPath)},
            extracted: true,
            alreadyExisted: true
          });
        }`
      );
      
      return; // Don't process further
    }
    if (typeof message === 'string' && message.startsWith('QUIXEL_OPEN_EXPLORER:')) {
      const filePath = message.substring('QUIXEL_OPEN_EXPLORER:'.length);

      // Normalize path separators for Windows
      const normalizedPath = filePath.replace(/\//g, path.sep);

      // Use shell.showItemInFolder to open file explorer
      shell.showItemInFolder(normalizedPath);
    }

    // Capture sign-in URL detection from injected script
    if (typeof message === 'string' && message.startsWith('QUIXEL_SIGNIN_URL:')) {
      const detectedUrl = message.substring('QUIXEL_SIGNIN_URL:'.length);

      // Only store if it's different from homepage (means it actually redirected)
      if (detectedUrl && !detectedUrl.includes('/megascans/home')) {
        if (!signInURL || signInURL !== detectedUrl) {
          signInURL = detectedUrl;

          // Mark initial auth check as complete since we now have the URL
          isInitialAuthCheck = false;
        }
      }
    }

    // Track download attempt start from injected script
    if (typeof message === 'string' && message.startsWith('QUIXEL_DOWNLOAD_ATTEMPT_START:')) {
      const timestamp = parseInt(message.substring('QUIXEL_DOWNLOAD_ATTEMPT_START:'.length));
      if (!isNaN(timestamp)) {
        downloadAttemptStartTime = timestamp;
      }
    }

    // ═══════════════════════════════════════════════════════════════
    // 🔍 ENHANCED ERROR DETECTION - Parse console errors for API failures
    // ═══════════════════════════════════════════════════════════════
    
    // Detect API errors from console messages (especially error level)
    if (level >= 2 && typeof message === 'string' && downloadAttemptStartTime !== null) {
      const timeSinceAttempt = Date.now() - downloadAttemptStartTime;
      
      // Only check errors that occur within 10 seconds of download attempt
      if (timeSinceAttempt < 10000) {
        // Check for API error patterns in console messages
        if (message.includes('Request failed with status code') ||
            message.includes('status code 400') ||
            message.includes('status code 401') ||
            message.includes('status code 403') ||
            message.includes('status code 404') ||
            message.includes('status code 500') ||
            message.includes('Cannot read properties of undefined') ||
            message.includes('Api Error Occurred') ||
            message.includes('Api Error')) {
          
          // Clear timeout
          if (downloadTimeoutId) {
            clearTimeout(downloadTimeoutId);
            downloadTimeoutId = null;
          }
          
          // Reset download attempt tracking
          downloadAttemptStartTime = null;
          
          // Extract status code if available
          const statusMatch = message.match(/status code (\d+)/);
          const statusCode = statusMatch ? statusMatch[1] : 'unknown';
          
          // Notify the page about the failure
          if (browserView) {
            browserView.webContents.executeJavaScript(
              `if (window.onDownloadFailed) {
                window.onDownloadFailed({
                  url: '${browserView.webContents.getURL()}',
                  error: 'API Error: Request failed with status code ${statusCode}'
                });
              }`
            );
          }
        }
      }
    }
  });

  // Track when URL changes (including hash/query params)
  browserView.webContents.on('did-navigate-in-page', (event, url, isMainFrame) => {
    if (isMainFrame) {
      // Update navigation button states
      updateNavigationButtonStates();
    }
  });

  // Track when new windows try to open (popups)
  browserView.webContents.setWindowOpenHandler((details) => {
    return { action: 'deny' }; // We'll handle it in the same window
  });

  // Open DevTools in development (optional - comment out for production)
  // browserView.webContents.openDevTools();
}

// Create system tray
function createTray() {
  tray = new Tray(path.join(__dirname, 'assets', 'images', 'windows_icon.ico'));

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Show Quixel Portal',
      click: () => {
        mainWindow.show();
        mainWindow.focus();
      }
    },
    {
      label: 'Hide to Tray',
      click: () => {
        mainWindow.hide();
      }
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => {
        isQuitting = true;

        // Save session before quitting
        if (browserView && browserView.webContents.session) {
          browserView.webContents.session.flushStorageData();
        }

        app.quit();
      }
    }
  ]);

  tray.setToolTip('Quixel Portal');
  tray.setContextMenu(contextMenu);

  // Double-click tray icon to show window
  tray.on('double-click', () => {
    if (mainWindow.isVisible()) {
      mainWindow.hide();
    } else {
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

// This method will be called when Electron has finished initialization
app.whenReady().then(() => {
  // Show splash screen first (instant!)
  createSplashScreen();

  // Create main window in background
  setTimeout(() => {
    createWindow();
    createTray();
  }, 500);

  app.on('activate', function () {
    // On macOS it's common to re-create a window in the app when the
    // dock icon is clicked and there are no other windows open
    if (BrowserWindow.getAllWindows().length === 0) {
      createSplashScreen();
      setTimeout(() => {
        createWindow();
      }, 500);
    }
  });
});

// ═══════════════════════════════════════════════════════════════
// 🚀 SOLUTION 1: Don't quit when window closes (run in background)
// ═══════════════════════════════════════════════════════════════

// Don't quit when all windows are closed - keep running in background
app.on('window-all-closed', function () {
  // On macOS, apps typically stay open even with no windows
  // On Windows/Linux, we now also keep it running for instant reopening
  // Don't quit - keep running in background
  // User can quit via tray menu
});

// ═══════════════════════════════════════════════════════════════
// 🚀 SOLUTION 4: SESSION PERSISTENCE - Save session regularly
// ═══════════════════════════════════════════════════════════════

// Flush session data periodically (every 30 seconds)
setInterval(() => {
  if (browserView && browserView.webContents.session) {
    browserView.webContents.session.flushStorageData();
  }
}, 30000); // Every 30 seconds

// Flush session before app quits
app.on('before-quit', () => {
  if (browserView && browserView.webContents.session) {
    browserView.webContents.session.flushStorageData();
  }
});

// IPC handlers for navigation
ipcMain.on('navigate-back', () => {
  if (browserView && browserView.webContents.canGoBack()) {
    browserView.webContents.goBack();
  }
});

ipcMain.on('navigate-forward', () => {
  if (browserView && browserView.webContents.canGoForward()) {
    browserView.webContents.goForward();
  }
});

ipcMain.on('navigate-home', (event, website) => {
  if (browserView) {
    // Use provided website or fall back to current selection
    const targetWebsite = website || currentWebsite;
    const url = WEBSITE_URLS[targetWebsite] || WEBSITE_URLS.quixel;
    browserView.webContents.loadURL(url);
  }
});

ipcMain.on('navigate-reload', () => {
  if (browserView) {
    browserView.webContents.reload();
  }
});

ipcMain.on('navigate-to', (event, url) => {
  if (browserView) {
    // Ensure the URL is valid
    try {
      new URL(url);
      browserView.webContents.loadURL(url);
    } catch (e) {
      // If not a valid URL, try to construct one
      const fullUrl = url.startsWith('http') ? url : `https://${url}`;
      browserView.webContents.loadURL(fullUrl);
    }
  }
});

// Website selection
ipcMain.on('set-current-website', (event, website) => {
  if (website === 'quixel' || website === 'polyhaven') {
    currentWebsite = website;
    console.log(`🌐 Current website changed to: ${website}`);
  }
});

// Window controls
ipcMain.on('window-minimize', () => {
  if (mainWindow) mainWindow.minimize();
});

ipcMain.on('window-maximize', () => {
  if (mainWindow) {
    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow.maximize();
    }
  }
});

ipcMain.on('window-close', () => {
  // Close button now hides to tray instead of closing completely
  if (mainWindow) mainWindow.hide();
});

// Window dragging handlers
let isDraggingWindow = false;
let dragStartPos = { x: 0, y: 0 };
let windowStartPos = { x: 0, y: 0 };

ipcMain.on('start-window-drag', (event, x, y) => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    isDraggingWindow = true;
    dragStartPos = { x, y };
    const bounds = mainWindow.getBounds();
    windowStartPos = { x: bounds.x, y: bounds.y };
  }
});

ipcMain.on('update-window-drag', (event, x, y) => {
  if (mainWindow && !mainWindow.isDestroyed() && isDraggingWindow) {
    const deltaX = x - dragStartPos.x;
    const deltaY = y - dragStartPos.y;
    mainWindow.setPosition(
      windowStartPos.x + deltaX,
      windowStartPos.y + deltaY
    );
  }
});

ipcMain.on('end-window-drag', () => {
  isDraggingWindow = false;
});

// Get navigation state
ipcMain.handle('get-navigation-state', () => {
  if (browserView) {
    return {
      canGoBack: browserView.webContents.canGoBack(),
      canGoForward: browserView.webContents.canGoForward()
    };
  }
  return { canGoBack: false, canGoForward: false };
});

// Show application menu
ipcMain.on('show-app-menu', (event, x, y) => {
  const template = [
    {
      label: 'File',
      submenu: [
        {
          label: 'New Window',
          accelerator: 'CmdOrCtrl+N',
          click: () => createWindow()
        },
        { type: 'separator' },
        {
          label: 'Close Window',
          accelerator: 'CmdOrCtrl+W',
          click: () => {
            if (mainWindow) mainWindow.close();
          }
        },
        { type: 'separator' },
        {
          label: 'Hide to Tray',
          accelerator: 'CmdOrCtrl+H',
          click: () => {
            if (mainWindow) mainWindow.hide();
          }
        },
        { type: 'separator' },
        {
          label: 'Quit',
          accelerator: 'CmdOrCtrl+Q',
          click: () => {
            isQuitting = true;
            if (browserView && browserView.webContents.session) {
              browserView.webContents.session.flushStorageData();
            }
            app.quit();
          }
        }
      ]
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' }
      ]
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' }
      ]
    },
    {
      label: 'Navigation',
      submenu: [
        {
          label: 'Back',
          accelerator: 'Alt+Left',
          click: () => {
            if (browserView && browserView.webContents.canGoBack()) {
              browserView.webContents.goBack();
            }
          }
        },
        {
          label: 'Forward',
          accelerator: 'Alt+Right',
          click: () => {
            if (browserView && browserView.webContents.canGoForward()) {
              browserView.webContents.goForward();
            }
          }
        },
        {
          label: 'Home',
          accelerator: 'CmdOrCtrl+H',
          click: () => {
            if (browserView) {
              browserView.webContents.loadURL('https://quixel.com/megascans/home');
            }
          }
        }
      ]
    },
    {
      label: 'Developer',
      submenu: [
        {
          label: 'Toggle DevTools',
          accelerator: 'F12',
          click: () => {
            if (browserView) {
              browserView.webContents.toggleDevTools();
            }
          }
        },
        { type: 'separator' },
        {
          label: 'Element Inspector',
          accelerator: 'F9',
          click: () => {
            enableElementInspector();
          }
        },
        { type: 'separator' },
        {
          label: 'Clear Cache and Reload',
          click: () => {
            if (browserView) {
              browserView.webContents.session.clearCache().then(() => {
                browserView.webContents.reload();
              });
            }
          }
        }
      ]
    }
  ];

  const menu = Menu.buildFromTemplate(template);
  menu.popup({
    window: mainWindow,
    x: Math.round(x),
    y: Math.round(y)
  });
});

// Show website selector dropdown (custom window)
ipcMain.on('show-website-menu', (event, x, y) => {
  // Close existing dropdown if open
  if (websiteDropdownWindow && !websiteDropdownWindow.isDestroyed()) {
    websiteDropdownWindow.close();
    websiteDropdownWindow = null;
    return;
  }

  // Get main window position
  const mainWindowBounds = mainWindow.getBounds();

  // Calculate absolute screen position
  // x, y are relative to the window content area
  const screenX = mainWindowBounds.x + Math.round(x);
  const screenY = mainWindowBounds.y + Math.round(y);

  // Create custom dropdown window (wider to accommodate submenu)
  websiteDropdownWindow = new BrowserWindow({
    width: 420, // Width for main menu (180) + submenu (220) + gap
    height: 400, // Taller to accommodate the largest submenu without scrolling
    x: screenX,
    y: screenY,
    frame: false,
    transparent: true,
    resizable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    parent: mainWindow,
    webPreferences: {
      preload: path.join(__dirname, 'website-dropdown-preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  // Remove menu bar
  websiteDropdownWindow.setMenuBarVisibility(false);

  // Load the dropdown HTML
  websiteDropdownWindow.loadFile('website-dropdown.html');

  // Auto-hide when it loses focus
  websiteDropdownWindow.on('blur', () => {
    // Small delay to prevent immediate close when clicking between elements
    setTimeout(() => {
      if (websiteDropdownWindow && !websiteDropdownWindow.isDestroyed()) {
        websiteDropdownWindow.close();
        websiteDropdownWindow = null;
      }
    }, 100);
  });

  // Clean up when closed
  websiteDropdownWindow.on('closed', () => {
    websiteDropdownWindow = null;
  });

  // Close dropdown when clicking on main window (including BrowserView)
  const closeDropdownOnClick = () => {
    if (websiteDropdownWindow && !websiteDropdownWindow.isDestroyed()) {
      websiteDropdownWindow.close();
      websiteDropdownWindow = null;
    }
  };

  // Listen for clicks on main window
  mainWindow.webContents.once('before-input-event', closeDropdownOnClick);

  // Listen for clicks on BrowserView
  if (browserView) {
    browserView.webContents.once('before-input-event', closeDropdownOnClick);
  }
});

// Handle website selection from dropdown
ipcMain.on('select-website', (event, website) => {
  currentWebsite = website;

  // Update UI in main window
  if (mainWindow) {
    mainWindow.webContents.send('website-changed', website);
  }

  // Navigate to selected website
  if (browserView) {
    browserView.webContents.loadURL(WEBSITE_URLS[website]);
  }
});

// Close dropdown window
ipcMain.on('close-dropdown', () => {
  if (websiteDropdownWindow && !websiteDropdownWindow.isDestroyed()) {
    websiteDropdownWindow.close();
    websiteDropdownWindow = null;
  }
});

// Note: Submenu is now handled within the dropdown window itself
// The show-submenu, request-submenu-data, and close-submenu handlers are no longer needed

// Execute submenu action
ipcMain.on('execute-submenu-action', (event, action) => {
  // Close dropdown window
  if (websiteDropdownWindow && !websiteDropdownWindow.isDestroyed()) {
    websiteDropdownWindow.close();
    websiteDropdownWindow = null;
  }

  // Execute the action
  switch (action) {
    // File actions
    case 'file-new-window':
      createWindow();
      break;
    case 'file-close-window':
      if (mainWindow) mainWindow.close();
      break;
    case 'file-hide-to-tray':
      if (mainWindow) mainWindow.hide();
      break;
    case 'file-quit':
      isQuitting = true;
      if (browserView && browserView.webContents.session) {
        browserView.webContents.session.flushStorageData();
      }
      app.quit();
      break;

    // Edit actions
    case 'edit-undo':
      if (browserView) browserView.webContents.undo();
      break;
    case 'edit-redo':
      if (browserView) browserView.webContents.redo();
      break;
    case 'edit-cut':
      if (browserView) browserView.webContents.cut();
      break;
    case 'edit-copy':
      if (browserView) browserView.webContents.copy();
      break;
    case 'edit-paste':
      if (browserView) browserView.webContents.paste();
      break;
    case 'edit-select-all':
      if (browserView) browserView.webContents.selectAll();
      break;

    // View actions
    case 'view-reload':
      if (browserView) browserView.webContents.reload();
      break;
    case 'view-force-reload':
      if (browserView) browserView.webContents.reloadIgnoringCache();
      break;
    case 'view-reset-zoom':
      if (browserView) browserView.webContents.setZoomLevel(0);
      break;
    case 'view-zoom-in':
      if (browserView) {
        const currentZoom = browserView.webContents.getZoomLevel();
        browserView.webContents.setZoomLevel(currentZoom + 0.5);
      }
      break;
    case 'view-zoom-out':
      if (browserView) {
        const currentZoom = browserView.webContents.getZoomLevel();
        browserView.webContents.setZoomLevel(currentZoom - 0.5);
      }
      break;
    case 'view-toggle-fullscreen':
      if (mainWindow) {
        mainWindow.setFullScreen(!mainWindow.isFullScreen());
      }
      break;

    // Navigation actions
    case 'nav-back':
      if (browserView && browserView.webContents.canGoBack()) {
        browserView.webContents.goBack();
      }
      break;
    case 'nav-forward':
      if (browserView && browserView.webContents.canGoForward()) {
        browserView.webContents.goForward();
      }
      break;
    case 'nav-home':
      if (browserView) {
        browserView.webContents.loadURL(WEBSITE_URLS[currentWebsite]);
      }
      break;

    // Developer actions
    case 'dev-toggle-devtools':
      if (browserView) {
        browserView.webContents.toggleDevTools();
      }
      break;
    case 'dev-element-inspector':
      enableElementInspector();
      break;
    case 'dev-clear-cache-reload':
      if (browserView) {
        browserView.webContents.session.clearCache().then(() => {
          browserView.webContents.reload();
        });
      }
      break;
  }
});

// ═══════════════════════════════════════════════════════════════
// 📥 DOWNLOADS PANEL IPC HANDLERS
// ═══════════════════════════════════════════════════════════════

// Toggle downloads panel
ipcMain.on('toggle-downloads-panel', () => {
  if (mainWindow) {
    mainWindow.webContents.send('toggle-downloads-panel');
  }
});

// Set downloads panel state (open/closed) to adjust BrowserView bounds
ipcMain.on('set-downloads-panel-state', (event, isOpen) => {
  if (global.setDownloadsPanelState) {
    global.setDownloadsPanelState(isOpen);
  }
});

// Get download history by scanning the Downloaded folder
ipcMain.handle('get-download-history', async () => {
  try {
    // Get the downloads path from localStorage or use default
    const userDataPath = app.getPath('userData');
    const defaultDownloadPath = path.join(os.homedir(), 'Documents', 'Quixel Portal', 'Downloaded');

    // Check if directory exists
    if (!fs.existsSync(defaultDownloadPath)) {
      return [];
    }

    const downloadHistory = [];
    const folders = fs.readdirSync(defaultDownloadPath);

    for (const folder of folders) {
      const folderPath = path.join(defaultDownloadPath, folder);

      // Skip if not a directory
      if (!fs.statSync(folderPath).isDirectory()) {
        continue;
      }

      try {
        // Find JSON file in the folder
        const files = fs.readdirSync(folderPath);
        const jsonFile = files.find(f => f.endsWith('.json'));

        if (!jsonFile) {
          continue;
        }

        // Read and parse JSON metadata
        const jsonPath = path.join(folderPath, jsonFile);
        const jsonContent = fs.readFileSync(jsonPath, 'utf8');
        const metadata = JSON.parse(jsonContent);

        // Find preview/thumbnail image
        let thumbnailPath = null;
        const previewFile = files.find(f =>
          f.toLowerCase().includes('_preview') ||
          f.toLowerCase().includes('preview')
        );

        if (previewFile) {
          thumbnailPath = path.join(folderPath, previewFile);
        }

        // Get folder creation/modification time
        const stats = fs.statSync(folderPath);

        // Extract data from metadata
        const assetName = metadata.semanticTags?.name || metadata.name || folder;
        const assetType = metadata.semanticTags?.asset_type || metadata.type || 'unknown';
        const assetId = metadata.id || folder;

        // Create cached thumbnail (64px version)
        let cachedThumbnail = null;
        if (thumbnailPath) {
          cachedThumbnail = createCachedThumbnail(thumbnailPath, assetId);
        }

        downloadHistory.push({
          id: assetId,
          name: assetName,
          type: assetType,
          path: folderPath,
          thumbnail: thumbnailPath,
          cachedThumbnail: cachedThumbnail, // Cached 64px version
          downloadDate: stats.mtime.getTime(), // milliseconds since epoch
          folderName: folder,
          metadata: {
            categories: metadata.categories || [],
            tags: metadata.tags || []
          }
        });

      } catch (error) {
        // Error parsing folder
      }
    }

    // Sort by most recent first
    downloadHistory.sort((a, b) => b.downloadDate - a.downloadDate);

    return downloadHistory;

  } catch (error) {
    return [];
  }
});

// Open folder in Windows Explorer
ipcMain.on('open-in-explorer', (event, folderPath) => {
  try {
    if (fs.existsSync(folderPath)) {
      // Open the folder directly instead of selecting it
      shell.openPath(folderPath);
    }
  } catch (error) {
    // Error opening folder
  }
});

// Get import history
ipcMain.handle('get-import-history', async () => {
  try {
    const userDataPath = app.getPath('userData');
    const historyFile = path.join(userDataPath, 'import_history.json');

    // Check if history file exists
    if (!fs.existsSync(historyFile)) {
      return [];
    }

    // Read and parse history
    const content = fs.readFileSync(historyFile, 'utf8');
    const history = JSON.parse(content);

    // Return imports array (already sorted by most recent first)
    return history.imports || [];

  } catch (error) {
    return [];
  }
});
