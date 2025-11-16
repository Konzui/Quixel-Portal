// Get elements
const appMenuBtn = document.getElementById('app-menu-btn');
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

// Store current URL and title
let currentURL = '';
let originalTitle = '';

// Menu state tracking
let isMenuOpen = false;
let lastMenuClickTime = 0;
const MENU_TOGGLE_DELAY = 300; // ms - time window for toggle detection

// App menu button - toggle behavior
appMenuBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  
  const now = Date.now();
  const timeSinceLastClick = now - lastMenuClickTime;
  
  // If menu was just opened (within toggle delay), treat this as a close action
  if (isMenuOpen && timeSinceLastClick < MENU_TOGGLE_DELAY) {
    isMenuOpen = false;
    lastMenuClickTime = 0;
    // Menu will close automatically, we just track the state
    return;
  }
  
  // Menu is closed or enough time has passed, open it
  isMenuOpen = true;
  lastMenuClickTime = now;
  const rect = appMenuBtn.getBoundingClientRect();
  window.electronAPI.showAppMenu(rect.left, rect.bottom);
  
  // Reset menu state after menu interaction time (menu auto-closes on outside click)
  setTimeout(() => {
    isMenuOpen = false;
    lastMenuClickTime = 0;
  }, 500);
});

// Close menu when clicking anywhere in the titlebar (outside the menu button)
titlebar.addEventListener('click', (e) => {
  // Don't close if clicking on the menu button itself (handled above)
  if (e.target.closest('#app-menu-btn')) {
    return;
  }

  // Don't close if clicking on the page title wrapper (handled separately)
  if (e.target.closest('#page-title-wrapper')) {
    return;
  }

  // Close menu if it's open
  if (isMenuOpen) {
    isMenuOpen = false;
    lastMenuClickTime = 0;
  }
}, true); // Use capture phase to catch clicks early

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
  window.electronAPI.navigateHome();
});

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
