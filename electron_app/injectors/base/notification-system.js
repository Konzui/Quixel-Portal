// Notification System - Download and import completion notifications
// Provides functions to show and hide notifications

module.exports = function() {
  return `
    // ═══════════════════════════════════════════════════════════════
    // 🔔 NOTIFICATION SYSTEM - User notifications for downloads/imports
    // ═══════════════════════════════════════════════════════════════
    
    // Create notification element if it doesn't exist
    function ensureNotificationElement() {
      let notification = document.getElementById('quixel-download-notification');
      if (!notification) {
        notification = document.createElement('div');
        notification.id = 'quixel-download-notification';
        document.body.appendChild(notification);
      }
      return notification;
    }

    // Function to show download completion notification
    function showDownloadNotification(downloadPath) {
      const notification = ensureNotificationElement();
      
      // Format the path for display (show only the relevant part)
      const pathParts = downloadPath.split(/[\\\\/]/);
      const displayPath = pathParts.length > 3 
        ? '...' + pathParts.slice(-3).join(' / ')
        : downloadPath;

      notification.innerHTML = \`
        <div class="notification-title">Download Completed</div>
        <div class="notification-message">Your download has been saved and extracted.</div>
        <div class="notification-path" data-path="\${downloadPath.replace(/\\\\/g, '\\\\\\\\')}">\${displayPath}</div>
      \`;

      // Add click handler to open file explorer
      const pathElement = notification.querySelector('.notification-path');
      pathElement.addEventListener('click', () => {
        // Use electronBridge to open file explorer
        if (window.electronBridge && window.electronBridge.openFileExplorer) {
          window.electronBridge.openFileExplorer(downloadPath);
        }
      });

      // Show notification
      setTimeout(() => {
        notification.classList.add('show');
      }, 10);

      // Auto-hide after 5 seconds
      setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => {
          notification.innerHTML = '';
        }, 300); // Wait for fade-out animation
      }, 5000);
    }

    // Function to hide notification
    function hideNotification(notification) {
      notification.classList.remove('show');
      setTimeout(() => {
        notification.innerHTML = '';
      }, 300); // Wait for fade-out animation
    }

    // Function to show import to Blender notification
    function showImportNotification(completionData) {
      const notification = ensureNotificationElement();

      const assetName = completionData.asset_name || 'Asset';
      const thumbnailHtml = completionData.thumbnailDataUrl
        ? \`<img src="\${completionData.thumbnailDataUrl}" class="notification-thumbnail" />\`
        : '<div class="notification-thumbnail-placeholder">No preview</div>';

      notification.innerHTML = \`
        <button class="notification-close" title="Close"></button>
        <div class="notification-content-with-thumb">
          \${thumbnailHtml}
          <div class="notification-text">
            <div class="notification-title">Import Complete</div>
            <div class="notification-message">\${assetName} got imported in Blender</div>
          </div>
        </div>
      \`;

      // Show notification
      setTimeout(() => {
        notification.classList.add('show');
      }, 10);

      // Auto-hide after 5 seconds (only if still showing)
      let autoHideTimeout = setTimeout(() => {
        if (notification.classList.contains('show')) {
          hideNotification(notification);
        }
      }, 5000);
      
      // Add click handler for close button
      const closeBtn = notification.querySelector('.notification-close');
      if (closeBtn) {
        closeBtn.addEventListener('click', () => {
          clearTimeout(autoHideTimeout);
          hideNotification(notification);
        });
      }
    }
    
    // Export functions to window for use by other modules
    window.showDownloadNotification = showDownloadNotification;
    window.showImportNotification = showImportNotification;
    window.hideNotification = hideNotification;
    
    // Set up download callbacks from main process
    window.onDownloadProgress = function(data) {
      // Clear timeout since download has started
      if (window.downloadTimeoutId) {
        clearTimeout(window.downloadTimeoutId);
        window.downloadTimeoutId = null;
      }
      window.downloadAttemptStartTime = null;
      
      if (window.currentDownloadButton) {
        updateProgressBar(window.currentDownloadButton, data.progress);
      }
    };

    window.onDownloadComplete = function(data) {
      // Clear timeout since download completed
      if (window.downloadTimeoutId) {
        clearTimeout(window.downloadTimeoutId);
        window.downloadTimeoutId = null;
      }
      window.downloadAttemptStartTime = null;
      
      if (window.currentDownloadButton) {
        updateProgressBar(window.currentDownloadButton, 100);

        // Change button text to "Importing" with animated dots
        if (window.currentDownloadButton._textElement) {
          window.currentDownloadButton._textElement.textContent = 'Importing';
          window.currentDownloadButton._textElement.classList.add('animated-dots');
        }

        // Don't auto-restore or show notification yet
        // Wait for Blender to send completion callback
      }

      // Don't show download complete notification - only show when import is done
    };

    window.onDownloadFailed = function(data) {
      // Clear timeout
      if (window.downloadTimeoutId) {
        clearTimeout(window.downloadTimeoutId);
        window.downloadTimeoutId = null;
      }
      window.downloadAttemptStartTime = null;
      
      if (window.currentDownloadButton) {
        removeProgressBar(window.currentDownloadButton);

        // Restore button text to original
        if (window.currentDownloadButton._textElement && window.currentDownloadButton.dataset.originalText) {
          window.currentDownloadButton._textElement.textContent = window.currentDownloadButton.dataset.originalText;
          window.currentDownloadButton._textElement.classList.remove('animated-dots');
        }

        window.currentDownloadButton = null;
      }

      alert('Download failed: ' + (data.error || 'Unknown error'));
    };
    
    // Listen for Blender import completion (set up via window object)
    window.onBlenderImportComplete = function(completionData) {
      // Restore button text to original
      if (window.currentDownloadButton) {
        removeProgressBar(window.currentDownloadButton);

        if (window.currentDownloadButton._textElement && window.currentDownloadButton.dataset.originalText) {
          window.currentDownloadButton._textElement.textContent = window.currentDownloadButton.dataset.originalText;
          window.currentDownloadButton._textElement.classList.remove('animated-dots');
        }

        window.currentDownloadButton = null;
      }

      // Show import complete notification with thumbnail
      showImportNotification(completionData);
    };
  `;
};

