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

// Page title wrapper click - copy URL to clipboard
pageTitleWrapper.addEventListener('click', async (e) => {
  e.stopPropagation();
  e.preventDefault();

  console.log('📋 Page title clicked, current URL:', currentURL);

  if (currentURL) {
    try {
      // Copy URL to clipboard using navigator.clipboard
      await navigator.clipboard.writeText(currentURL);
      console.log('✅ URL copied to clipboard:', currentURL);

      // Store the current title
      const titleBeforeCopy = pageTitle.textContent;

      // Show copied state on the wrapper (blue background)
      pageTitleWrapper.classList.add('copied');

      // Change title to "URL Copied"
      pageTitle.textContent = 'URL Copied';

      // Restore title and remove copied state after 1.2 seconds
      setTimeout(() => {
        pageTitleWrapper.classList.remove('copied');
        pageTitle.textContent = titleBeforeCopy;
      }, 1200);
    } catch (error) {
      console.error('❌ Failed to copy URL:', error);
    }
  } else {
    console.warn('⚠️ No URL available to copy');
  }
});
