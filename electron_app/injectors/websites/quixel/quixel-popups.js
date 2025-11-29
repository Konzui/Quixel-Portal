// Quixel Popups - Popup removal logic for Quixel website
// Removes annoying modals and banners

module.exports = function() {
  return `
    // ═══════════════════════════════════════════════════════════════
    // 🚫 QUIXEL POPUPS - Remove annoying modals and banners
    // ═══════════════════════════════════════════════════════════════
    
    // Function to aggressively remove the Megascans popup
    function removeMegascansPopup() {
      let removed = false;

      // Remove the modal popup
      const modalContent = document.querySelector('div.modalContent___1Vd1b');
      if (modalContent) {
        // Try to find and remove the parent modal
        let parent = modalContent.parentElement;
        while (parent && parent !== document.body) {
          if (parent.className && (
              parent.className.includes('modal') ||
              parent.className.includes('Modal') ||
              parent.className.includes('overlay') ||
              parent.className.includes('Overlay')
          )) {
            parent.remove();
            removed = true;
            break;
          }
          parent = parent.parentElement;
        }
        // If no modal parent found, just remove the content
        if (!removed && modalContent.parentElement) {
          modalContent.remove();
          removed = true;
        }
      }

      // Remove the Fab banner
      const fabBanner = document.querySelector('div.css-1uaj9x');
      if (fabBanner) {
        fabBanner.remove();
        removed = true;
      }

      // Also check for parent container
      const fabBannerParent = document.querySelector('div.css-1ymlmsw');
      if (fabBannerParent) {
        fabBannerParent.remove();
        removed = true;
      }

      return removed;
    }

    // Remove popup and banner immediately if they exist
    removeMegascansPopup();

    // Monitor DOM for popup appearing and remove it
    const popupObserver = new MutationObserver(() => {
      removeMegascansPopup();
    });

    popupObserver.observe(document.body, {
      childList: true,
      subtree: true
    });

    // Also check periodically for the first 5 seconds (catches late-loading popups)
    let popupCheckCount = 0;
    const popupCheckInterval = setInterval(() => {
      removeMegascansPopup();
      popupCheckCount++;
      if (popupCheckCount >= 10) { // 10 checks * 500ms = 5 seconds
        clearInterval(popupCheckInterval);
      }
    }, 500);
    
    // Auto sign-in redirect on startup (one-time check)
    function checkAndRedirectToSignIn() {
      // Only run once
      if (window.signInCheckComplete) {
        return;
      }

      const signInButton = document.querySelector('button.css-xwv3p2');
      if (signInButton && signInButton.textContent.toLowerCase().includes('sign in')) {
        // Listen for URL changes to see where it redirects
        const originalPushState = history.pushState;
        history.pushState = function(...args) {
          return originalPushState.apply(this, arguments);
        };

        const originalReplaceState = history.replaceState;
        history.replaceState = function(...args) {
          return originalReplaceState.apply(this, arguments);
        };

        // Click the sign-in button
        signInButton.click();

        // Check URL after click
        setTimeout(() => {
          const newUrl = window.location.href;
          // Send the sign-in URL to console with special prefix for main process to detect
          if (window.sendToElectron) {
            window.sendToElectron('SIGNIN_URL', newUrl);
          } else {
            console.log('QUIXEL_SIGNIN_URL:' + newUrl);
          }
        }, 100);

        setTimeout(() => {
          const newUrl = window.location.href;
          // Send again in case it changed
          if (window.sendToElectron) {
            window.sendToElectron('SIGNIN_URL', newUrl);
          } else {
            console.log('QUIXEL_SIGNIN_URL:' + newUrl);
          }
        }, 500);

        setTimeout(() => {
          const newUrl = window.location.href;

          // Final check
          if (window.sendToElectron) {
            window.sendToElectron('SIGNIN_URL', newUrl);
          } else {
            console.log('QUIXEL_SIGNIN_URL:' + newUrl);
          }
        }, 1000);

        // Mark as complete so we don't check again
        window.signInCheckComplete = true;
      }
    }

    // Check for sign-in button after a short delay (let page load first)
    setTimeout(() => {
      checkAndRedirectToSignIn();
    }, 1000);

    // Also check a few more times in case the button loads late
    setTimeout(() => {
      checkAndRedirectToSignIn();
    }, 2000);

    setTimeout(() => {
      checkAndRedirectToSignIn();
    }, 3000);
  `;
};

