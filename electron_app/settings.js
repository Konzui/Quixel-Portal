// Settings window JavaScript

// DOM Elements
const closeBtn = document.getElementById('close-settings-btn');
const downloadPathInput = document.getElementById('download-path-input');
const browsePathBtn = document.getElementById('browse-path-btn');
const glacierToggle = document.getElementById('glacier-setup-toggle');

// Settings state
let currentSettings = {
  downloadPath: '',
  glacierSetup: true
};

// Initialize settings on page load
async function initializeSettings() {
  try {
    // Get settings from localStorage (via main process)
    const settings = await window.settingsAPI.getSettings();

    if (settings) {
      currentSettings = settings;
      updateUI();
    }
  } catch (error) {
    console.error('Failed to load settings:', error);
  }
}

// Update UI with current settings
function updateUI() {
  downloadPathInput.value = currentSettings.downloadPath || '';
  glacierToggle.checked = currentSettings.glacierSetup;
}

// Save settings
function saveSettings() {
  window.settingsAPI.saveSettings(currentSettings);
}

// Event Listeners

// Close button
closeBtn.addEventListener('click', () => {
  window.settingsAPI.closeSettings();
});

// Browse path button
browsePathBtn.addEventListener('click', async () => {
  try {
    const selectedPath = await window.settingsAPI.selectDownloadPath();
    if (selectedPath) {
      currentSettings.downloadPath = selectedPath;
      downloadPathInput.value = selectedPath;
      saveSettings();
    }
  } catch (error) {
    console.error('Failed to select path:', error);
  }
});

// Glacier toggle
glacierToggle.addEventListener('change', () => {
  currentSettings.glacierSetup = glacierToggle.checked;
  saveSettings();
});

// Listen for settings updates from main process
window.settingsAPI.onSettingsUpdated((settings) => {
  currentSettings = settings;
  updateUI();
});

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
  // Close on Escape
  if (e.key === 'Escape') {
    window.settingsAPI.closeSettings();
  }

  // Close on Ctrl/Cmd + W
  if ((e.ctrlKey || e.metaKey) && e.key === 'w') {
    e.preventDefault();
    window.settingsAPI.closeSettings();
  }
});

// Initialize on page load
initializeSettings();
