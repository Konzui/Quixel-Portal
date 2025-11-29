// Quixel Auth - API request interception and queuing
// Handles authentication state and queues API requests until auth is ready

module.exports = function() {
  return `
    // ═══════════════════════════════════════════════════════════════
    // 🔒 API REQUEST INTERCEPTION & QUEUING - Prevent race condition
    // ═══════════════════════════════════════════════════════════════
    
    // Debug flag - controls verbose logging (set to true to enable debug logs)
    const DEBUG_AUTH = true; // Always enabled for API call tracking
    
    // Helper function for API call logging (always logs API calls)
    function logApiCall(reason, url, method, details) {
      const timestamp = new Date().toISOString();
      const methodStr = method ? method.toUpperCase() : 'GET';
      console.log(\`[API CALL] \${timestamp} | \${methodStr} | \${url}\`);
      console.log(\`  📋 REASON: \${reason}\`);
      if (details) {
        console.log(\`  ℹ️  DETAILS: \${details}\`);
      }
    }
    
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
        logApiCall('Auth polling - checking if authentication is ready', testUrl, 'GET', 'Polling every ' + AUTH_POLL_INTERVAL + 'ms to detect when auth becomes available');
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
        logApiCall('Releasing queued API call', queuedRequest.url, queuedRequest.method || 'GET', 'This request was queued earlier and is now being sent because authentication is ready. Queue position: #' + (index + 1));
        debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' 📤 Releasing queued request #' + (index + 1) + ': ' + queuedRequest.url);
        
        if (queuedRequest.type === 'fetch') {
          // Execute the original fetch
          queuedRequest.originalFetch(queuedRequest.url, queuedRequest.options)
            .then(response => {
              logApiCall('Queued API call completed', queuedRequest.url, queuedRequest.method || 'GET', 'Status: ' + response.status);
              debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ✅ Queued fetch completed: ' + queuedRequest.url + ' (status: ' + response.status + ')');
              queuedRequest.resolve(response);
            })
            .catch(error => {
              logApiCall('Queued API call failed', queuedRequest.url, queuedRequest.method || 'GET', 'Error: ' + error.message);
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
            logApiCall('Releasing queued XHR call', queuedRequest.url, queuedRequest.method || 'GET', 'This XHR request was queued earlier and is now being sent because authentication is ready');
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
          logApiCall('Auth endpoint - checking user authentication status', fetchUrl, options?.method || 'GET', 'This endpoint is used to verify if user is logged in. Allowed immediately to check auth state.');
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
          logApiCall('API call - auth ready, sending immediately', fetchUrl, options?.method || 'GET', 'Authentication confirmed, request sent directly');
          debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ✅ Auth ready, allowing fetch: ' + fetchUrl);
          return originalFetch.apply(this, arguments);
        }
        
        // Allow first API request through immediately to test auth
        if (!window.quixelFirstApiRequestSent) {
          window.quixelFirstApiRequestSent = true;
          logApiCall('First API call - testing authentication', fetchUrl, options?.method || 'GET', 'First API request is used to test if authentication is ready. Response will determine if we queue subsequent requests.');
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
          logApiCall('API call - grace period passed, sending request', fetchUrl, options?.method || 'GET', 'Grace period (' + AUTH_GRACE_PERIOD + 'ms) has passed. Sending request even if auth not confirmed yet.');
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
        logApiCall('API call QUEUED - waiting for authentication', fetchUrl, options?.method || 'GET', 'Request queued because auth is not ready yet. Will be sent when authentication is confirmed. ' + remainingTime + 'ms remaining in grace period.');
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
            logApiCall('Auth endpoint - checking authentication status', requestUrl, requestMethod, 'This endpoint verifies if user is logged in. Allowed immediately to check auth state.');
            return originalSend.call(this, body);
          }
          
          // Regular API endpoint
          // If auth is ready, proceed normally (no monitoring needed)
          if (window.quixelAuthReady) {
            logApiCall('API XHR - sending request', requestUrl, requestMethod, 'Authentication confirmed, XHR request sent');
            debugLog('[QUIXEL AUTH] ' + getTimestamp() + ' ✅ Auth ready, sending XHR: ' + requestUrl);
            return originalSend.call(this, body);
          }
          
          // If this is the first request and it was already opened, just send it
          // (monitoring was already added in open())
          // Note: isQueued is set in open() if the request was queued
          if (window.quixelFirstApiRequestSent) {
            // Check if request was queued by checking if open was called
            // If we're here and it's the first request, it means open() already executed
            logApiCall('First API XHR - testing authentication', requestUrl, requestMethod, 'First XHR request is used to test if authentication is ready');
            return originalSend.call(this, body);
          }
          
          // Check if grace period has passed
          const timeSinceStart = Date.now() - window.quixelAuthCheckStartTime;
          if (timeSinceStart >= AUTH_GRACE_PERIOD) {
            logApiCall('API XHR - grace period passed, sending request', requestUrl, requestMethod, 'Grace period (' + AUTH_GRACE_PERIOD + 'ms) has passed. Sending XHR request even if auth not confirmed yet.');
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
            logApiCall('API XHR QUEUED - waiting for authentication', requestUrl, requestMethod, 'XHR request queued because auth is not ready yet. Will be sent when authentication is confirmed.');
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
            logApiCall('API XHR - releasing queued request', requestUrl, requestMethod, 'This XHR was queued earlier and is now being sent because authentication is ready');
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
  `;
};

