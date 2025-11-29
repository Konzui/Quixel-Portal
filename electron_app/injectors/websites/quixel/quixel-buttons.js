// Quixel Buttons - Button detection, modification, and click handling
// Detects download buttons, modifies their text, and handles click events

module.exports = function() {
  return `
    // ═══════════════════════════════════════════════════════════════
    // 🔘 QUIXEL BUTTONS - Button detection and modification
    // ═══════════════════════════════════════════════════════════════
    
    // Debounce helper to prevent duplicate searches
    let searchTimeout = null;
    let lastSearchTime = 0;

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
              // Extract asset ID from URL
              const finalAssetId = window.extractAssetIdFromUrl ? window.extractAssetIdFromUrl() : null;
              
              // If we have an asset ID, check if it exists locally before allowing API call
              if (finalAssetId) {
                // Use asset utils to check if asset exists
                if (window.checkAssetExists) {
                  window.checkAssetExists(finalAssetId, function(exists, path) {
                    if (exists && path) {
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
                      if (window.importExistingAsset) {
                        window.importExistingAsset(path);
                      } else if (window.sendToElectron) {
                        window.sendToElectron('IMPORT_ASSET', path);
                      } else {
                        console.log('QUIXEL_IMPORT_EXISTING_ASSET:' + path);
                      }
                      return; // Exit early, don't allow normal flow
                    } else {
                      // Asset doesn't exist - update UI first, then allow normal download flow
                      // Change button text to "Downloading" with animated dots
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
                        if (window.sendToElectron) {
                          window.sendToElectron('DOWNLOAD_START', window.downloadAttemptStartTime.toString());
                        } else {
                          console.log('QUIXEL_DOWNLOAD_ATTEMPT_START:' + window.downloadAttemptStartTime);
                        }
                        
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
                      
                      // Now allow the event to propagate to Quixel's handler to start the download
                      // Don't prevent default or stop propagation - let it happen naturally
                    }
                  });
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
                if (window.sendToElectron) {
                  window.sendToElectron('DOWNLOAD_START', window.downloadAttemptStartTime.toString());
                } else {
                  console.log('QUIXEL_DOWNLOAD_ATTEMPT_START:' + window.downloadAttemptStartTime);
                }

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
    if (window.setupUrlObserver) {
      window.setupUrlObserver(function(newUrl) {
        // Check if asset detail opened
        const urlParams = new URLSearchParams(new URL(newUrl).search);
        const assetId = urlParams.get('assetId');
        if (assetId) {
          // Search immediately, then again after longer delay to ensure React has finished rendering
          window.findDownloadButton(true);
          setTimeout(() => window.findDownloadButton(), 500);
        }
      });
    }

    // Monitor DOM changes to detect new download buttons (silent)
    if (window.setupDOMObserver) {
      window.setupDOMObserver((mutations) => {
        if (searchTimeout) clearTimeout(searchTimeout);
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
            window.findDownloadButton();
          }
        }, 200); // Increased from 100ms to 200ms to reduce processing during rapid DOM changes
      });
    }

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

      // Get saved Glacier setup preference
      const savedGlacierSetup = localStorage.getItem('quixelGlacierSetup');
      const glacierEnabled = savedGlacierSetup === null ? true : savedGlacierSetup === 'true';

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

          <!-- Glacier Setup toggle row -->
          <div class="subContainer___2ALnu" style="margin-right: 16px; padding-left: 24px; padding-right: 24px; margin-top: 16px;">
            <div class="left___2S9Lx">
              <span class="label___2h7yz">Enable Glacier Setup</span>
              <span style="display: block; font-size: 11px; color: rgba(255, 255, 255, 0.5); margin-top: 4px;">
                Import assets with optimized Glacier material settings
              </span>
            </div>
            <div class="right___38KOV">
              <label class="quixel-toggle-switch" style="
                position: relative;
                display: inline-block;
                width: 48px;
                height: 24px;
              ">
                <input
                  id="quixel-glacier-setup-toggle"
                  type="checkbox"
                  \${glacierEnabled ? 'checked' : ''}
                  style="opacity: 0; width: 0; height: 0;"
                />
                <span class="quixel-toggle-slider" style="
                  position: absolute;
                  cursor: pointer;
                  top: 0;
                  left: 0;
                  right: 0;
                  bottom: 0;
                  background-color: \${glacierEnabled ? '#4CAF50' : '#333'};
                  transition: 0.3s;
                  border-radius: 24px;
                ">
                  <span style="
                    position: absolute;
                    content: '';
                    height: 18px;
                    width: 18px;
                    left: \${glacierEnabled ? '27px' : '3px'};
                    bottom: 3px;
                    background-color: white;
                    transition: 0.3s;
                    border-radius: 50%;
                  "></span>
                </span>
              </label>
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
      const glacierToggle = document.getElementById('quixel-glacier-setup-toggle');

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

          // Trigger storage event for settings window sync
          window.dispatchEvent(new StorageEvent('storage', {
            key: 'quixelDownloadPath',
            newValue: pathInput.value,
            storageArea: localStorage
          }));
        });

        // Load saved path from localStorage
        const savedPath = localStorage.getItem('quixelDownloadPath');
        if (savedPath) {
          pathInput.value = savedPath;
          window.quixelDownloadPath = savedPath;
        }
      }

      // Glacier Setup toggle event listener
      if (glacierToggle) {
        glacierToggle.addEventListener('change', () => {
          const isEnabled = glacierToggle.checked;
          localStorage.setItem('quixelGlacierSetup', isEnabled.toString());

          // Update toggle appearance
          const slider = glacierToggle.nextElementSibling;
          const knob = slider.querySelector('span');
          slider.style.backgroundColor = isEnabled ? '#4CAF50' : '#333';
          knob.style.left = isEnabled ? '27px' : '3px';
        });

        // Listen for storage events (when settings change from global settings window)
        window.addEventListener('storage', (e) => {
          if (e.key === 'quixelGlacierSetup' && glacierToggle) {
            const newValue = e.newValue === 'true';
            if (glacierToggle.checked !== newValue) {
              glacierToggle.checked = newValue;
              const slider = glacierToggle.nextElementSibling;
              const knob = slider.querySelector('span');
              slider.style.backgroundColor = newValue ? '#4CAF50' : '#333';
              knob.style.left = newValue ? '27px' : '3px';
            }
          }

          if (e.key === 'quixelDownloadPath' && pathInput) {
            if (pathInput.value !== e.newValue) {
              pathInput.value = e.newValue;
              window.quixelDownloadPath = e.newValue;
            }
          }
        });
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
  `;
};

