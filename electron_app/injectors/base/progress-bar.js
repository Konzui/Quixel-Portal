// Progress Bar - UI components for download progress indicators
// Provides functions to add, update, and remove progress bars from buttons

module.exports = function() {
  return `
    // ═══════════════════════════════════════════════════════════════
    // 📊 PROGRESS BAR - Download progress UI components
    // ═══════════════════════════════════════════════════════════════
    
    // Function to add linear progress indicator below download button
    function addProgressBarToButton(button) {
      // Check if progress indicator already exists
      if (button.querySelector('.quixel-linear-progress-container')) {
        return;
      }

      // Make button position relative if not already
      if (window.getComputedStyle(button).position === 'static') {
        button.style.position = 'relative';
      }

      // Create linear progress container
      const progressContainer = document.createElement('div');
      progressContainer.className = 'quixel-linear-progress-container';
      
      // Create progress fill bar
      const progressFill = document.createElement('div');
      progressFill.className = 'quixel-linear-progress-fill';
      
      // Create progress text (percentage)
      const progressText = document.createElement('div');
      progressText.className = 'quixel-linear-progress-text';
      progressText.textContent = '0%';
      
      progressContainer.appendChild(progressFill);
      progressContainer.appendChild(progressText);
      button.appendChild(progressContainer);
      button.dataset.quixelDownloading = 'true';
    }

    // Function to update linear progress
    function updateProgressBar(button, progress) {
      const progressFill = button.querySelector('.quixel-linear-progress-fill');
      const progressText = button.querySelector('.quixel-linear-progress-text');
      
      if (progressFill) {
        progressFill.style.width = progress + '%';
      }
      
      if (progressText) {
        progressText.textContent = Math.round(progress) + '%';
      }
    }

    // Function to remove progress bar
    function removeProgressBar(button) {
      const progressContainer = button.querySelector('.quixel-linear-progress-container');
      if (progressContainer) {
        progressContainer.remove();
      }
      delete button.dataset.quixelDownloading;
    }
    
    // Export functions to window for use by other modules
    window.addProgressBarToButton = addProgressBarToButton;
    window.updateProgressBar = updateProgressBar;
    window.removeProgressBar = removeProgressBar;
  `;
};

