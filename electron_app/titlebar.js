// Get elements
const backBtn = document.getElementById('back-btn');
const forwardBtn = document.getElementById('forward-btn');
const reloadBtn = document.getElementById('reload-btn');
const homeBtn = document.getElementById('home-btn');
const downloadsBtn = document.getElementById('downloads-btn');
const minimizeBtn = document.getElementById('minimize-btn');
const maximizeBtn = document.getElementById('maximize-btn');
const closeBtn = document.getElementById('close-btn');
const pageTitle = document.getElementById('page-title');
const pageTitleWrapper = document.getElementById('page-title-wrapper');
const titlebar = document.getElementById('titlebar');

// Website selector elements
const websiteSelectorBtn = document.getElementById('website-selector-btn');
const websiteDropdown = document.getElementById('website-dropdown');
const websiteIcon = document.getElementById('website-icon');
const websiteName = document.getElementById('website-name');
const websiteOptions = document.querySelectorAll('.website-option');

// Store current URL and title
let currentURL = '';
let originalTitle = '';

// Store current website selection
let currentWebsite = 'quixel'; // Default to Quixel

// Navigation buttons
backBtn.addEventListener('click', () => {
  window.electronAPI.navigateBack();
});

forwardBtn.addEventListener('click', () => {
  window.electronAPI.navigateForward();
});

reloadBtn.addEventListener('click', () => {
  window.electronAPI.navigateReload();
});

homeBtn.addEventListener('click', () => {
  window.electronAPI.navigateHome(currentWebsite);
});

// Website selector - show native menu
websiteSelectorBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  const rect = websiteSelectorBtn.getBoundingClientRect();
  window.electronAPI.showWebsiteMenu(rect.left, rect.bottom);
});

// Listen for website changes from main process
if (window.electronAPI.onWebsiteChanged) {
  window.electronAPI.onWebsiteChanged((event, website) => {
    // Update current website
    currentWebsite = website;

    // Update UI
    if (website === 'quixel') {
      websiteIcon.src = 'assets/icons/quixel_24.png';
      websiteName.textContent = 'Quixel';
    } else if (website === 'polyhaven') {
      websiteIcon.src = 'assets/icons/polyhaven_24.svg';
      websiteName.textContent = 'Polyhaven';
    }
  });
}

// Downloads button
downloadsBtn.addEventListener('click', () => {
  window.electronAPI.toggleDownloadsPanel();
});

// Window control buttons
minimizeBtn.addEventListener('click', () => {
  window.electronAPI.windowMinimize();
});

maximizeBtn.addEventListener('click', () => {
  window.electronAPI.windowMaximize();
});

closeBtn.addEventListener('click', () => {
  window.electronAPI.windowClose();
});

// Listen for navigation started to capture URL
window.electronAPI.onNavigationStarted((event, url) => {
  console.log('🔗 Navigation started:', url);
  if (url) {
    currentURL = url;
  }
});

// Listen for navigation events from main process
window.electronAPI.onNavigationFinished((event, data) => {
  backBtn.disabled = !data.canGoBack;
  forwardBtn.disabled = !data.canGoForward;

  // Store current URL
  if (data.url) {
    currentURL = data.url;
    console.log('🔗 Current URL updated:', currentURL);
  }
});

// Listen for page title updates
if (window.electronAPI.onPageTitleUpdated) {
  window.electronAPI.onPageTitleUpdated((event, title) => {
    if (title) {
      originalTitle = title;
      pageTitle.textContent = title;
    }
  });
}

// Page title wrapper - handle both drag and click
let dragStartX = 0;
let dragStartY = 0;
let dragStartTime = 0;
let isDraggingWindow = false;
let copyRestoreTimeout = null; // Track timeout for restoring title after copy
const DRAG_THRESHOLD = 5; // pixels - if mouse moves more than this, it's a drag
const CLICK_MAX_TIME = 200; // ms - if mouse is held longer, it might be a drag

pageTitleWrapper.addEventListener('mousedown', (e) => {
  // Store initial mouse position and time (both client and screen coordinates)
  dragStartX = e.clientX;
  dragStartY = e.clientY;
  const dragStartScreenX = e.screenX;
  const dragStartScreenY = e.screenY;
  dragStartTime = Date.now();
  isDraggingWindow = false;
  
  // Track mouse movement during drag
  const handleMouseMove = (moveEvent) => {
    const deltaX = Math.abs(moveEvent.clientX - dragStartX);
    const deltaY = Math.abs(moveEvent.clientY - dragStartY);
    
    // If moved beyond threshold, it's a drag - start window dragging
    if (deltaX > DRAG_THRESHOLD || deltaY > DRAG_THRESHOLD) {
      if (!isDraggingWindow) {
        isDraggingWindow = true;
        // Start window drag using Electron API with initial screen coordinates
        window.electronAPI.startWindowDrag(dragStartScreenX, dragStartScreenY);
      }
      // Update window position during drag
      window.electronAPI.updateWindowDrag(moveEvent.screenX, moveEvent.screenY);
    }
  };
  
  const handleMouseUp = async (upEvent) => {
    // Calculate if this was a click or drag (using client coordinates for click detection)
    const deltaX = Math.abs(upEvent.clientX - dragStartX);
    const deltaY = Math.abs(upEvent.clientY - dragStartY);
    const deltaTime = Date.now() - dragStartTime;
    
    // End window drag if it was active
    if (isDraggingWindow) {
      window.electronAPI.endWindowDrag();
    }
    
    // Only trigger copy if it was a click (not a drag)
    // Check: small movement AND short time = click
    if (!isDraggingWindow && deltaX <= DRAG_THRESHOLD && deltaY <= DRAG_THRESHOLD && deltaTime < CLICK_MAX_TIME) {
      upEvent.stopPropagation();
      upEvent.preventDefault();

      if (currentURL) {
        try {
          // Clear any existing restore timeout to prevent conflicts
          if (copyRestoreTimeout) {
            clearTimeout(copyRestoreTimeout);
            copyRestoreTimeout = null;
          }

          // Store the original title (use the stored original or current if not in copied state)
          let titleBeforeCopy;
          if (pageTitleWrapper.classList.contains('copied')) {
            // If already in copied state, we need to get the original from a data attribute
            titleBeforeCopy = pageTitleWrapper.dataset.originalTitle || originalTitle || 'Quixel Portal';
          } else {
            titleBeforeCopy = pageTitle.textContent;
            // Store original title in data attribute for future reference
            pageTitleWrapper.dataset.originalTitle = titleBeforeCopy;
          }

          // Copy URL to clipboard using navigator.clipboard
          await navigator.clipboard.writeText(currentURL);

          // Show copied state on the wrapper (blue background)
          pageTitleWrapper.classList.add('copied');

          // Change title to "URL Copied"
          pageTitle.textContent = 'URL Copied';

          // Restore title and remove copied state after 1.2 seconds
          copyRestoreTimeout = setTimeout(() => {
            pageTitleWrapper.classList.remove('copied');
            pageTitle.textContent = titleBeforeCopy;
            copyRestoreTimeout = null;
          }, 1200);
        } catch (error) {
          // Failed to copy URL
        }
      }
    }
    
    // Clean up listeners
    document.removeEventListener('mousemove', handleMouseMove);
    document.removeEventListener('mouseup', handleMouseUp);
    
    // Reset drag tracking
    dragStartX = 0;
    dragStartY = 0;
    dragStartTime = 0;
    isDraggingWindow = false;
  };
  
  // Add listeners to document to track movement even if mouse leaves the element
  document.addEventListener('mousemove', handleMouseMove);
  document.addEventListener('mouseup', handleMouseUp);
});
