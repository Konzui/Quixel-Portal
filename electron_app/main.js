const { app, BrowserWindow, BrowserView, ipcMain, Menu, session, dialog, shell, Tray, nativeImage } = require('electron');
const path = require('path');
const os = require('os');
const fs = require('fs');
const extractZip = require('extract-zip');
const generateInjectionScript = require('./injectors');

let mainWindow;
let browserView;
let tray = null;
let isQuitting = false;
let splashWindow = null;
let websiteDropdownWindow = null;
let submenuWindow = null;
let currentSubmenuType = null;
let settingsWindow = null;

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

  // Detect website from current URL or use currentWebsite variable
  let website = currentWebsite;
  try {
    const url = browserView.webContents.getURL();
    if (url.includes('quixel.com')) {
      website = 'quixel';
    } else if (url.includes('polyhaven.com')) {
      website = 'polyhaven';
    }
  } catch (e) {
    // URL not available yet, use currentWebsite
  }

  // Generate injection script using the modular injector system
  const debugScript = generateInjectionScript(website);

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

async function sendImportRequestToBlender(assetPath) {
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

    // Get Glacier setup preference from localStorage (async)
    let glacierSetup = true; // Default to enabled
    if (browserView && browserView.webContents) {
      try {
        const glacierPref = await browserView.webContents.executeJavaScript(
          'localStorage.getItem("quixelGlacierSetup")'
        );
        glacierSetup = glacierPref === null ? true : glacierPref === 'true';
      } catch (err) {
        // Use default if unable to read
      }
    }

    // Write import request with thumbnail, name, type, Glacier setup, and Blender instance ID
    const requestData = {
      asset_path: assetPath,
      thumbnail: thumbnailPath,
      asset_name: assetName,
      asset_type: assetType,
      glacier_setup: glacierSetup, // Include Glacier setup preference
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
    // Handle dropdown close request from BrowserView
    if (typeof message === 'string' && message.startsWith('QUIXEL_CLOSE_DROPDOWN:')) {
      if (websiteDropdownWindow && !websiteDropdownWindow.isDestroyed()) {
        websiteDropdownWindow.close();
        websiteDropdownWindow = null;
      }
      return;
    }
    
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

  // Get main window position - use getContentBounds() for accurate positioning in fullscreen
  // getContentBounds() returns the content area bounds, which is what we need
  const mainWindowBounds = mainWindow.getContentBounds();
  const isFullscreen = mainWindow.isFullScreen();

  // Calculate absolute screen position
  // x, y are relative to the window content area
  // In fullscreen mode, getContentBounds() already accounts for the screen position
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

  // Global click handler that works for both titlebar and BrowserView
  // Define this first so it can be used in closeDropdown
  let globalClickHandler = null;

  // Close dropdown function
  const closeDropdown = () => {
    if (websiteDropdownWindow && !websiteDropdownWindow.isDestroyed()) {
      websiteDropdownWindow.close();
      websiteDropdownWindow = null;
    }
    // Remove global click listeners
    if (globalClickHandler) {
      mainWindow.webContents.removeListener('before-input-event', globalClickHandler);
      if (browserView) {
        browserView.webContents.removeListener('before-input-event', globalClickHandler);
      }
      globalClickHandler = null;
    }
  };

  // Create global click handler that works for both titlebar and BrowserView
  globalClickHandler = (event, input) => {
    // Only close on mouse clicks, not keyboard events
    if (input && (input.type === 'mouseDown' || input.type === 'mouseUp')) {
      closeDropdown();
    }
  };

  // Listen for clicks on main window (titlebar)
  mainWindow.webContents.on('before-input-event', globalClickHandler);

  // Listen for clicks on BrowserView (website content)
  if (browserView) {
    browserView.webContents.on('before-input-event', globalClickHandler);
    
    // Also inject a click handler into the BrowserView for more reliable detection
    // This catches clicks that might not trigger before-input-event
    // Only inject if dropdown is actually open
    if (websiteDropdownWindow && !websiteDropdownWindow.isDestroyed()) {
      const clickHandlerScript = `
        (function() {
          // Remove existing handler if any
          if (window._quixelDropdownClickHandler) {
            document.removeEventListener('click', window._quixelDropdownClickHandler, true);
          }
          
          window._quixelDropdownClickHandler = function(e) {
            // Send message to main process to close dropdown
            console.log('QUIXEL_CLOSE_DROPDOWN:click');
            // Remove handler after first click
            document.removeEventListener('click', window._quixelDropdownClickHandler, true);
            window._quixelDropdownClickHandler = null;
          };
          
          // Add click listener to document (capture phase to catch all clicks)
          document.addEventListener('click', window._quixelDropdownClickHandler, true);
        })();
      `;
      
      browserView.webContents.executeJavaScript(clickHandlerScript).catch(() => {
        // Ignore errors if page isn't ready
      });
    }
  }

  // Clean up when closed
  websiteDropdownWindow.on('closed', () => {
    // Remove global click listeners when dropdown closes
    if (globalClickHandler) {
      mainWindow.webContents.removeListener('before-input-event', globalClickHandler);
      if (browserView) {
        browserView.webContents.removeListener('before-input-event', globalClickHandler);
      }
      globalClickHandler = null;
    }
    websiteDropdownWindow = null;
  });

  // Auto-hide when it loses focus (backup mechanism)
  websiteDropdownWindow.on('blur', () => {
    // Small delay to prevent immediate close when clicking between elements
    setTimeout(() => {
      if (websiteDropdownWindow && !websiteDropdownWindow.isDestroyed()) {
        // Only close if dropdown is not focused (user clicked elsewhere)
        if (!websiteDropdownWindow.isFocused()) {
          closeDropdown();
        }
      }
    }, 100);
  });
});

// Handle close dropdown request (called from dropdown window)
ipcMain.on('close-dropdown', () => {
  if (websiteDropdownWindow && !websiteDropdownWindow.isDestroyed()) {
    websiteDropdownWindow.close();
    websiteDropdownWindow = null;
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

    // Settings actions
    case 'settings-open':
      createSettingsWindow();
      break;
  }
});

// ═══════════════════════════════════════════════════════════════
// ⚙️ SETTINGS WINDOW
// ═══════════════════════════════════════════════════════════════

// Create settings window
function createSettingsWindow() {
  // If settings window already exists, focus it
  if (settingsWindow && !settingsWindow.isDestroyed()) {
    settingsWindow.focus();
    return;
  }

  // Create settings window
  settingsWindow = new BrowserWindow({
    width: 900,
    height: 600,
    frame: false,
    transparent: false,
    resizable: false,
    skipTaskbar: false,
    parent: mainWindow,
    modal: true,
    backgroundColor: '#1a1a1a',
    webPreferences: {
      preload: path.join(__dirname, 'settings-preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    },
    icon: path.join(__dirname, 'assets', 'images', 'windows_icon.ico')
  });

  // Remove menu bar
  settingsWindow.setMenuBarVisibility(false);

  // Load settings HTML
  settingsWindow.loadFile('settings.html');

  // Handle window close
  settingsWindow.on('closed', () => {
    settingsWindow = null;
  });

  // Center on parent window
  if (mainWindow && !mainWindow.isDestroyed()) {
    const mainBounds = mainWindow.getBounds();
    const settingsBounds = settingsWindow.getBounds();
    const x = Math.round(mainBounds.x + (mainBounds.width - settingsBounds.width) / 2);
    const y = Math.round(mainBounds.y + (mainBounds.height - settingsBounds.height) / 2);
    settingsWindow.setPosition(x, y);
  }
}

// Close settings window
ipcMain.on('close-settings', () => {
  if (settingsWindow && !settingsWindow.isDestroyed()) {
    settingsWindow.close();
    settingsWindow = null;
  }
});

// Select download path using dialog
ipcMain.handle('select-download-path', async () => {
  const result = await dialog.showOpenDialog(settingsWindow || mainWindow, {
    properties: ['openDirectory'],
    title: 'Select Download Location',
    defaultPath: path.join(os.homedir(), 'Documents', 'Quixel Portal')
  });

  if (!result.canceled && result.filePaths.length > 0) {
    return result.filePaths[0];
  }

  return null;
});

// Get current settings from localStorage (via BrowserView session)
ipcMain.handle('get-settings', async () => {
  if (!browserView || !browserView.webContents) {
    return {
      downloadPath: path.join(os.homedir(), 'Documents', 'Quixel Portal'),
      glacierSetup: true
    };
  }

  try {
    // Execute JavaScript in BrowserView to get localStorage values
    const downloadPath = await browserView.webContents.executeJavaScript(
      'localStorage.getItem("quixelDownloadPath") || null'
    );
    const glacierSetup = await browserView.webContents.executeJavaScript(
      'localStorage.getItem("quixelGlacierSetup")'
    );

    return {
      downloadPath: downloadPath || path.join(os.homedir(), 'Documents', 'Quixel Portal'),
      glacierSetup: glacierSetup === null ? true : glacierSetup === 'true'
    };
  } catch (error) {
    console.error('Failed to get settings from localStorage:', error);
    return {
      downloadPath: path.join(os.homedir(), 'Documents', 'Quixel Portal'),
      glacierSetup: true
    };
  }
});

// Save settings to localStorage (via BrowserView session)
ipcMain.on('save-settings', async (event, settings) => {
  if (!browserView || !browserView.webContents) {
    return;
  }

  try {
    // Update localStorage in BrowserView
    await browserView.webContents.executeJavaScript(`
      localStorage.setItem('quixelDownloadPath', ${JSON.stringify(settings.downloadPath)});
      localStorage.setItem('quixelGlacierSetup', ${JSON.stringify(settings.glacierSetup.toString())});

      // Trigger storage event for in-page settings sync
      window.dispatchEvent(new StorageEvent('storage', {
        key: 'quixelDownloadPath',
        newValue: ${JSON.stringify(settings.downloadPath)},
        oldValue: localStorage.getItem('quixelDownloadPath'),
        storageArea: localStorage
      }));

      window.dispatchEvent(new StorageEvent('storage', {
        key: 'quixelGlacierSetup',
        newValue: ${JSON.stringify(settings.glacierSetup.toString())},
        oldValue: localStorage.getItem('quixelGlacierSetup'),
        storageArea: localStorage
      }));
    `);

    console.log('Settings saved:', settings);
  } catch (error) {
    console.error('Failed to save settings to localStorage:', error);
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
