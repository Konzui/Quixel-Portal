// Wait for submenu data from main process
window.addEventListener('DOMContentLoaded', () => {
  // Request submenu data
  window.electronAPI.requestSubmenuData();
});

// Listen for submenu data
if (window.electronAPI.onSubmenuData) {
  window.electronAPI.onSubmenuData((event, items) => {
    const container = document.getElementById('submenu-container');
    container.innerHTML = '';

    items.forEach(item => {
      if (item.type === 'separator') {
        const separator = document.createElement('div');
        separator.className = 'submenu-separator';
        container.appendChild(separator);
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
          window.electronAPI.closeSubmenu();
        });

        container.appendChild(button);
      }
    });
  });
}

// Close submenu when window loses focus
window.addEventListener('blur', () => {
  window.electronAPI.closeSubmenu();
});

// Prevent default context menu
document.addEventListener('contextmenu', (e) => {
  e.preventDefault();
});
