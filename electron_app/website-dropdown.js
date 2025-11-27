// Get all menu option buttons
const menuOptions = document.querySelectorAll('.menu-option');
const submenuPanel = document.getElementById('submenu-panel');
let currentActiveMenuItem = null;

// Submenu data
const submenuData = {
  file: [
    { label: 'New Window', accelerator: 'Ctrl+N', action: 'file-new-window' },
    { type: 'separator' },
    { label: 'Close Window', accelerator: 'Ctrl+W', action: 'file-close-window' },
    { type: 'separator' },
    { label: 'Hide to Tray', accelerator: 'Ctrl+H', action: 'file-hide-to-tray' },
    { type: 'separator' },
    { label: 'Quit', accelerator: 'Ctrl+Q', action: 'file-quit' }
  ],
  edit: [
    { label: 'Undo', accelerator: 'Ctrl+Z', action: 'edit-undo' },
    { label: 'Redo', accelerator: 'Ctrl+Y', action: 'edit-redo' },
    { type: 'separator' },
    { label: 'Cut', accelerator: 'Ctrl+X', action: 'edit-cut' },
    { label: 'Copy', accelerator: 'Ctrl+C', action: 'edit-copy' },
    { label: 'Paste', accelerator: 'Ctrl+V', action: 'edit-paste' },
    { label: 'Select All', accelerator: 'Ctrl+A', action: 'edit-select-all' }
  ],
  view: [
    { label: 'Reload', accelerator: 'Ctrl+R', action: 'view-reload' },
    { label: 'Force Reload', accelerator: 'Ctrl+Shift+R', action: 'view-force-reload' },
    { type: 'separator' },
    { label: 'Reset Zoom', accelerator: 'Ctrl+0', action: 'view-reset-zoom' },
    { label: 'Zoom In', accelerator: 'Ctrl++', action: 'view-zoom-in' },
    { label: 'Zoom Out', accelerator: 'Ctrl+-', action: 'view-zoom-out' },
    { type: 'separator' },
    { label: 'Toggle Fullscreen', accelerator: 'F11', action: 'view-toggle-fullscreen' }
  ],
  navigation: [
    { label: 'Back', accelerator: 'Alt+Left', action: 'nav-back' },
    { label: 'Forward', accelerator: 'Alt+Right', action: 'nav-forward' },
    { label: 'Home', action: 'nav-home' }
  ],
  developer: [
    { label: 'Toggle DevTools', accelerator: 'F12', action: 'dev-toggle-devtools' },
    { type: 'separator' },
    { label: 'Element Inspector', accelerator: 'F9', action: 'dev-element-inspector' },
    { type: 'separator' },
    { label: 'Clear Cache and Reload', action: 'dev-clear-cache-reload' }
  ]
};

// Function to show submenu
function showSubmenu(submenuType, targetElement) {
  const items = submenuData[submenuType];
  if (!items) return;

  // Remove active class from previous menu item
  if (currentActiveMenuItem) {
    currentActiveMenuItem.classList.remove('active-submenu');
  }

  // Add active class to current menu item
  if (targetElement) {
    targetElement.classList.add('active-submenu');
    currentActiveMenuItem = targetElement;
  }

  // Clear existing submenu
  submenuPanel.innerHTML = '';

  // Populate submenu
  items.forEach(item => {
    if (item.type === 'separator') {
      const separator = document.createElement('div');
      separator.className = 'submenu-separator';
      submenuPanel.appendChild(separator);
    } else {
      const button = document.createElement('button');
      button.className = 'submenu-item';

      const label = document.createElement('span');
      label.className = 'submenu-item-label';
      label.textContent = item.label;
      button.appendChild(label);

      if (item.accelerator) {
        const accelerator = document.createElement('span');
        accelerator.className = 'submenu-accelerator';
        accelerator.textContent = item.accelerator;
        button.appendChild(accelerator);
      }

      button.addEventListener('click', () => {
        window.electronAPI.executeSubmenuAction(item.action);
        window.electronAPI.closeDropdown();
      });

      submenuPanel.appendChild(button);
    }
  });

  // Position submenu at the same height as the hovered item
  if (targetElement) {
    const rect = targetElement.getBoundingClientRect();
    const containerRect = document.querySelector('.dropdown-container').getBoundingClientRect();
    const topOffset = rect.top - containerRect.top;
    submenuPanel.style.top = `${topOffset}px`;
  }

  // Show submenu panel
  submenuPanel.classList.add('active');
}

// Function to hide submenu
function hideSubmenu() {
  submenuPanel.classList.remove('active');

  // Remove active class from menu item
  if (currentActiveMenuItem) {
    currentActiveMenuItem.classList.remove('active-submenu');
    currentActiveMenuItem = null;
  }
}

// Handle menu option clicks and hovers
menuOptions.forEach(option => {
  // Click handler for website selection
  option.addEventListener('click', () => {
    // Check if it's a website selection
    const website = option.dataset.website;
    if (website) {
      // Send website selection to main process
      window.electronAPI.selectWebsite(website);
      // Close the dropdown window
      window.electronAPI.closeDropdown();
      return;
    }
  });

  // Hover handler for submenu triggers
  option.addEventListener('mouseenter', () => {
    // Check if it's a submenu trigger
    const submenu = option.dataset.submenu;
    if (submenu) {
      showSubmenu(submenu, option);
    } else {
      // Hide submenu when hovering over non-submenu items
      hideSubmenu();
    }
  });
});

// Hide submenu when mouse leaves the menu section
const menuSection = document.querySelector('.menu-section');
const dropdownMenu = document.querySelector('.dropdown-menu');

// Add mouseleave to dropdown menu to hide submenu when leaving the menu area
dropdownMenu.addEventListener('mouseleave', (e) => {
  // Check if mouse is moving to submenu
  const submenuRect = submenuPanel.getBoundingClientRect();
  const isMovingToSubmenu = e.clientX >= submenuRect.left &&
                            e.clientX <= submenuRect.right &&
                            e.clientY >= submenuRect.top &&
                            e.clientY <= submenuRect.bottom;

  if (!isMovingToSubmenu) {
    hideSubmenu();
  }
});

// Keep submenu visible when hovering over it
submenuPanel.addEventListener('mouseenter', () => {
  // Submenu stays visible
});

submenuPanel.addEventListener('mouseleave', () => {
  // Hide submenu when leaving submenu
  hideSubmenu();
});

// Close dropdown when clicking outside (window loses focus)
window.addEventListener('blur', () => {
  window.electronAPI.closeDropdown();
});

// Prevent default context menu
document.addEventListener('contextmenu', (e) => {
  e.preventDefault();
});
