// ═══════════════════════════════════════════════════════════════
// 📥 DOWNLOADS PANEL FUNCTIONALITY
// ═══════════════════════════════════════════════════════════════

const downloadsPanel = document.getElementById('downloads-panel');
const downloadsBackdrop = document.getElementById('downloads-backdrop');
const closePanelBtn = document.getElementById('close-panel-btn');
const downloadsList = document.getElementById('downloads-list');
const openExplorerBtn = document.getElementById('open-explorer-btn');
const downloadsTab = document.getElementById('downloads-tab');
const importsTab = document.getElementById('imports-tab');
const downloadsBtnIcon = document.getElementById('downloads-btn-icon');

let currentDownloads = [];
let currentImports = [];
let activeDownloadId = null;
let activeTab = 'downloads'; // 'downloads' or 'imports'

// ═══════════════════════════════════════════════════════════════
// PANEL TOGGLE
// ═══════════════════════════════════════════════════════════════

function togglePanel(forceOpen = false) {
  const isOpen = downloadsPanel.classList.contains('open');

  if (forceOpen || !isOpen) {
    downloadsPanel.classList.add('open');
    // Update icon to open state
    if (downloadsBtnIcon) {
      downloadsBtnIcon.src = 'assets/icons/right_sidepanel_open_24.svg';
    }
    // Load the active tab's content
    if (activeTab === 'downloads') {
      loadDownloadHistory();
    } else {
      loadImportHistory();
    }
    // Notify main process to adjust BrowserView bounds
    window.electronAPI.setDownloadsPanelState(true);
  } else {
    downloadsPanel.classList.remove('open');
    // Update icon to closed state
    if (downloadsBtnIcon) {
      downloadsBtnIcon.src = 'assets/icons/right_sidepanel_closed_24.svg';
    }
    // Notify main process to restore BrowserView bounds
    window.electronAPI.setDownloadsPanelState(false);
  }
}

// Close panel button
closePanelBtn.addEventListener('click', () => {
  downloadsPanel.classList.remove('open');
  // Update icon to closed state
  if (downloadsBtnIcon) {
    downloadsBtnIcon.src = 'assets/icons/right_sidepanel_closed_24.svg';
  }
  // Notify main process to restore BrowserView bounds
  window.electronAPI.setDownloadsPanelState(false);
});

// Listen for toggle events from main process via IPC
if (window.electronAPI.onToggleDownloadsPanel) {
  window.electronAPI.onToggleDownloadsPanel(() => {
    togglePanel();
  });
}

// Click outside to close
document.addEventListener('click', (e) => {
  const isOpen = downloadsPanel.classList.contains('open');
  const clickedInside = downloadsPanel.contains(e.target);
  const clickedDownloadsBtn = e.target.closest('#downloads-btn');

  if (isOpen && !clickedInside && !clickedDownloadsBtn) {
    downloadsPanel.classList.remove('open');
    // Update icon to closed state
    if (downloadsBtnIcon) {
      downloadsBtnIcon.src = 'assets/icons/right_sidepanel_closed_24.svg';
    }
    window.electronAPI.setDownloadsPanelState(false);
  }
});

// ═══════════════════════════════════════════════════════════════
// TAB SWITCHING
// ═══════════════════════════════════════════════════════════════

function switchTab(tabName) {
  activeTab = tabName;

  // Update tab button states
  if (tabName === 'downloads') {
    downloadsTab.classList.add('active');
    importsTab.classList.remove('active');
    loadDownloadHistory();
  } else {
    importsTab.classList.add('active');
    downloadsTab.classList.remove('active');
    loadImportHistory();
  }
}

// Tab click handlers
downloadsTab.addEventListener('click', () => {
  switchTab('downloads');
});

importsTab.addEventListener('click', () => {
  switchTab('imports');
});

// ═══════════════════════════════════════════════════════════════
// LOAD DOWNLOAD HISTORY
// ═══════════════════════════════════════════════════════════════

async function loadDownloadHistory() {
  try {
    console.log('📥 Loading download history...');
    const downloads = await window.electronAPI.getDownloadHistory();
    currentDownloads = downloads;
    renderDownloads(downloads);
  } catch (error) {
    console.error('📥 Error loading download history:', error);
    renderEmpty('downloads');
  }
}

// ═══════════════════════════════════════════════════════════════
// LOAD IMPORT HISTORY
// ═══════════════════════════════════════════════════════════════

async function loadImportHistory() {
  try {
    console.log('📦 Loading import history...');
    const imports = await window.electronAPI.getImportHistory();
    currentImports = imports;
    renderImports(imports);
  } catch (error) {
    console.error('📦 Error loading import history:', error);
    renderEmpty('imports');
  }
}

// ═══════════════════════════════════════════════════════════════
// RENDER DOWNLOADS
// ═══════════════════════════════════════════════════════════════

function renderDownloads(downloads) {
  if (!downloads || downloads.length === 0) {
    renderEmpty('downloads');
    return;
  }

  downloadsList.innerHTML = '';

  downloads.forEach(download => {
    const item = createDownloadItem(download);
    downloadsList.appendChild(item);
  });
}

function renderImports(imports) {
  if (!imports || imports.length === 0) {
    renderEmpty('imports');
    return;
  }

  downloadsList.innerHTML = '';

  imports.forEach(importItem => {
    const item = createImportItem(importItem);
    downloadsList.appendChild(item);
  });
}

function renderEmpty(type = 'downloads') {
  const message = type === 'downloads' ? 'No downloads yet' : 'No imports yet';
  downloadsList.innerHTML = `
    <div class="downloads-empty">
      <p>${message}</p>
    </div>
  `;
}

// ═══════════════════════════════════════════════════════════════
// CREATE DOWNLOAD ITEM
// ═══════════════════════════════════════════════════════════════

function createDownloadItem(download) {
  const item = document.createElement('div');
  item.className = 'download-item';
  item.dataset.id = download.id;
  item.dataset.path = download.path;

  // Format date
  const date = new Date(download.downloadDate);
  const formattedDate = formatDate(date);

  // Get asset type class
  const typeClass = getTypeClass(download.type);

  // Create thumbnail HTML using shared function
  const thumbnailHTML = createThumbnailHTML(download.thumbnail, download.cachedThumbnail, download.name, download.type);

  item.innerHTML = `
    ${thumbnailHTML}
    <div class="download-info">
      <p class="download-name" title="${download.name}">${download.name}</p>
      <div class="download-meta">
        <span class="download-type ${typeClass}">${download.type}</span>
        <span class="download-meta-separator">•</span>
        <span class="download-date">${formattedDate}</span>
      </div>
    </div>
    <button class="open-folder-btn" title="Open in Explorer">
      <img src="assets/icons/folder_24.svg" alt="Folder">
    </button>
  `;

  // Add click handler for open folder button
  const folderBtn = item.querySelector('.open-folder-btn');
  folderBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    openFolder(download.path);
  });

  // Add click handler for thumbnail to navigate to asset page
  const thumbnail = item.querySelector('.download-thumbnail');
  if (thumbnail) {
    thumbnail.addEventListener('click', (e) => {
      e.stopPropagation();
      navigateToAsset(download.id);
    });
  }

  // Add click handler for asset name to navigate to asset page
  const assetName = item.querySelector('.download-name');
  if (assetName) {
    assetName.addEventListener('click', (e) => {
      e.stopPropagation();
      navigateToAsset(download.id);
    });
  }

  return item;
}

function createImportItem(importData) {
  const item = document.createElement('div');
  item.className = 'download-item';
  item.dataset.id = importData.id;
  item.dataset.path = importData.assetPath;

  // Format date - use importTimestamp
  const date = new Date(importData.importTimestamp);
  const formattedDate = formatDate(date);

  // Get asset type class
  const typeClass = getTypeClass(importData.assetType);

  // Create thumbnail HTML using shared function
  const thumbnailHTML = createThumbnailHTML(importData.thumbnail, importData.cachedThumbnail, importData.assetName, importData.assetType);

  item.innerHTML = `
    ${thumbnailHTML}
    <div class="download-info">
      <p class="download-name" title="${importData.assetName}">${importData.assetName}</p>
      <div class="download-meta">
        <span class="download-type ${typeClass}">${importData.assetType}</span>
        <span class="download-meta-separator">•</span>
        <span class="download-date">Imported ${formattedDate}</span>
      </div>
    </div>
    <button class="open-folder-btn" title="Open in Explorer">
      <img src="assets/icons/folder_24.svg" alt="Folder">
    </button>
  `;

  // Add click handler for open folder button
  const folderBtn = item.querySelector('.open-folder-btn');
  folderBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    openFolder(importData.assetPath);
  });

  // Add click handler for thumbnail to navigate to asset page
  const thumbnail = item.querySelector('.download-thumbnail');
  if (thumbnail) {
    thumbnail.addEventListener('click', (e) => {
      e.stopPropagation();
      navigateToAsset(importData.assetId);
    });
  }

  // Add click handler for asset name to navigate to asset page
  const assetName = item.querySelector('.download-name');
  if (assetName) {
    assetName.addEventListener('click', (e) => {
      e.stopPropagation();
      navigateToAsset(importData.assetId);
    });
  }

  return item;
}

// ═══════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════

function createThumbnailHTML(thumbnail, cachedThumbnail, altText, assetType) {
  // Create thumbnail element with fallback chain
  let thumbnailHTML;
  if (thumbnail || cachedThumbnail) {
    // Primary: Try original thumbnail
    const primaryUrl = thumbnail ? `file:///${thumbnail.replace(/\\/g, '/')}` : null;
    // Fallback: Try cached thumbnail
    const fallbackUrl = cachedThumbnail ? `file:///${cachedThumbnail.replace(/\\/g, '/')}` : null;

    if (primaryUrl && fallbackUrl) {
      // Both available - use primary with fallback
      thumbnailHTML = `<img src="${primaryUrl}" class="download-thumbnail" alt="${altText}" onerror="this.src='${fallbackUrl}'; this.onerror=function(){this.className='download-thumbnail no-image'; this.innerHTML='${getTypeIcon(assetType)}'; this.removeAttribute('src');};">`;
    } else if (primaryUrl) {
      // Only primary available
      thumbnailHTML = `<img src="${primaryUrl}" class="download-thumbnail" alt="${altText}" onerror="this.className='download-thumbnail no-image'; this.innerHTML='${getTypeIcon(assetType)}'; this.removeAttribute('src');">`;
    } else if (fallbackUrl) {
      // Only cached available
      thumbnailHTML = `<img src="${fallbackUrl}" class="download-thumbnail" alt="${altText}" onerror="this.className='download-thumbnail no-image'; this.innerHTML='${getTypeIcon(assetType)}'; this.removeAttribute('src');">`;
    }
  } else {
    thumbnailHTML = `<div class="download-thumbnail no-image">${getTypeIcon(assetType)}</div>`;
  }
  return thumbnailHTML;
}

function getTypeClass(type) {
  const typeMap = {
    '3d': 'type-3d',
    'surface': 'type-surface',
    'decal': 'type-decal',
    '3dplant': 'type-3d'
  };
  return typeMap[type.toLowerCase()] || 'type-decal';
}

function getTypeIcon(type) {
  const iconMap = {
    '3d': '3D',
    'surface': 'SF',
    'decal': 'DC',
    '3dplant': '3D'
  };
  return iconMap[type.toLowerCase()] || 'DL';
}

function formatDate(date) {
  const now = new Date();
  const diffTime = Math.abs(now - date);
  const diffMinutes = Math.floor(diffTime / (1000 * 60));
  const diffHours = Math.floor(diffTime / (1000 * 60 * 60));
  const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));

  if (diffMinutes < 1) {
    return 'Just now';
  } else if (diffMinutes < 60) {
    return `${diffMinutes} min ago`;
  } else if (diffHours < 24) {
    return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
  } else if (diffDays === 1) {
    return 'Yesterday';
  } else if (diffDays < 7) {
    return `${diffDays} days ago`;
  } else {
    const options = { month: 'short', day: 'numeric', year: 'numeric' };
    return date.toLocaleDateString('en-US', options);
  }
}

function openFolder(folderPath) {
  console.log('📂 Opening folder:', folderPath);
  window.electronAPI.openInExplorer(folderPath);
}

function navigateToAsset(assetId) {
  console.log('🔗 Navigating to asset:', assetId);
  if (!assetId) {
    console.warn('⚠️ No asset ID provided');
    return;
  }

  // Construct the Megascans URL with the asset ID
  const megascansUrl = `https://quixel.com/megascans/home?assetId=${assetId}`;

  // Use the navigation API to navigate to the asset page
  window.electronAPI.navigateTo(megascansUrl);

  // Keep the downloads panel open - don't close it
}

// ═══════════════════════════════════════════════════════════════
// FOOTER BUTTONS
// ═══════════════════════════════════════════════════════════════

openExplorerBtn.addEventListener('click', () => {
  // Open the main Downloads folder
  if (currentDownloads.length > 0) {
    // Get parent folder from the first download
    const firstDownload = currentDownloads[0];
    const parentFolder = firstDownload.path.substring(0, firstDownload.path.lastIndexOf('\\'));
    openFolder(parentFolder);
  } else {
    // If no downloads, still try to open the default folder
    // We'll send a path that the main process can validate
    openFolder('C:\\Users\\' + (process.env.USERNAME || 'Benutzer1') + '\\Documents\\Quixel Portal\\Downloaded');
  }
});

// ═══════════════════════════════════════════════════════════════
// DOWNLOAD PROGRESS TRACKING
// ═══════════════════════════════════════════════════════════════

// Listen for download events from main process
if (window.electronAPI.onDownloadStarted) {
  window.electronAPI.onDownloadStarted((event, data) => {
    console.log('📥 Download started:', data);
    // Don't auto-open panel on download start
  });
}

if (window.electronAPI.onDownloadProgress) {
  window.electronAPI.onDownloadProgress((event, data) => {
    console.log('📥 Download progress:', data);
    updateDownloadProgress(data);
  });
}

if (window.electronAPI.onDownloadCompleted) {
  window.electronAPI.onDownloadCompleted((event, data) => {
    console.log('📥 Download completed:', data);
    // Reload the download history to show the new download (only if downloads tab is active)
    if (activeTab === 'downloads') {
      setTimeout(() => {
        loadDownloadHistory();
      }, 1000);
    }
  });
}

// Listen for Blender import completion to update import history
if (window.electronAPI.onBlenderImportComplete) {
  window.electronAPI.onBlenderImportComplete((event, data) => {
    console.log('📦 Import completed:', data);
    // Reload the import history to show the new import
    // Do this regardless of active tab so it's ready when user switches
    setTimeout(() => {
      loadImportHistory();
    }, 1000);
  });
}

function updateDownloadProgress(data) {
  // Create or update active download item
  // This will be implemented when we hook into the actual download flow
  console.log('Progress update:', data);
}

// ═══════════════════════════════════════════════════════════════
// INITIALIZE
// ═══════════════════════════════════════════════════════════════

console.log('📥 Downloads panel initialized');
