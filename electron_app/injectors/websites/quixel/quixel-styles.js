// Quixel Styles - CSS injection for Quixel website
// Injects custom styles for buttons, notifications, progress bars, etc.

module.exports = function() {
  return `
    // ═══════════════════════════════════════════════════════════════
    // 🎨 QUIXEL STYLES - Custom CSS injection
    // ═══════════════════════════════════════════════════════════════
    
    // Inject CSS for instant custom background on download buttons + hide annoying popup
    const styleElement = document.createElement('style');
    styleElement.id = 'quixel-download-style';
    styleElement.textContent = \`
      /* Target download buttons - will apply instantly when they appear */
      button.Button___1mkoh.Button--fullWidth___2subI {
        background: #0C8CE9 !important;
        background-color: #0C8CE9 !important;
        color: white !important;
        border: 2px solid #0C8CE9 !important;
        border-color: #0C8CE9 !important;
      }

      /* Hide the annoying "A NEW HOME FOR MEGASCANS" popup */
      div.modalContent___1Vd1b {
        display: none !important;
      }

      /* Also hide the modal overlay/backdrop */
      [class*="modalOverlay"],
      [class*="Modal"],
      div[class*="modal"][class*="Overlay"] {
        display: none !important;
      }

      /* Hide the annoying "Megascans have a new home on Fab" banner */
      div.css-1uaj9x {
        display: none !important;
      }

      /* Also target parent container if needed */
      div.css-1ymlmsw {
        display: none !important;
      }

      /* Linear progress bar styles */
      .quixel-linear-progress-container {
        position: absolute;
        bottom: -2px;
        left: 0;
        width: 100%;
        height: 2px;
        background: rgba(255, 255, 255, 0.1);
        overflow: visible;
      }

      .quixel-linear-progress-fill {
        height: 100%;
        background: rgba(255, 255, 255, 0.8);
        width: 0%;
        transition: width 0.3s ease;
      }

      .quixel-linear-progress-text {
        position: absolute;
        right: 0;
        bottom: 4px;
        font-size: 11px;
        color: rgba(255, 255, 255, 0.7);
        font-weight: 500;
        pointer-events: none;
        white-space: nowrap;
      }

      /* Download notification styles */
      #quixel-download-notification {
        position: fixed;
        bottom: 20px;
        left: 20px;
        background: #1a1a1a;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 6px;
        padding: 10px 14px;
        padding-right: 32px;
        min-width: 250px;
        max-width: 350px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        z-index: 10000;
        opacity: 0;
        transform: translateY(20px);
        transition: opacity 0.3s ease, transform 0.3s ease;
        pointer-events: none;
      }

      #quixel-download-notification.show {
        opacity: 1;
        transform: translateY(0);
        pointer-events: auto;
      }
      
      /* Close button for notification */
      #quixel-download-notification .notification-close {
        position: absolute;
        top: 8px;
        right: 8px;
        width: 20px;
        height: 20px;
        cursor: pointer;
        opacity: 0.6;
        transition: opacity 0.2s;
        display: flex;
        align-items: center;
        justify-content: center;
        border: none;
        background: transparent;
        padding: 0;
      }
      
      #quixel-download-notification .notification-close:hover {
        opacity: 1;
      }
      
      #quixel-download-notification .notification-close::before,
      #quixel-download-notification .notification-close::after {
        content: '';
        position: absolute;
        width: 12px;
        height: 2px;
        background: rgba(255, 255, 255, 0.8);
        border-radius: 1px;
      }
      
      #quixel-download-notification .notification-close::before {
        transform: rotate(45deg);
      }
      
      #quixel-download-notification .notification-close::after {
        transform: rotate(-45deg);
      }

      #quixel-download-notification .notification-title {
        color: rgba(255, 255, 255, 0.9);
        font-size: 13px;
        font-weight: 500;
        margin-bottom: 4px;
      }

      #quixel-download-notification .notification-message {
        color: rgba(255, 255, 255, 0.7);
        font-size: 12px;
        margin-bottom: 4px;
      }

      #quixel-download-notification .notification-path {
        color: rgba(255, 255, 255, 0.8);
        font-size: 11px;
        cursor: pointer;
        text-decoration: underline;
        text-decoration-color: rgba(255, 255, 255, 0.3);
        transition: text-decoration-color 0.2s;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      #quixel-download-notification .notification-path:hover {
        text-decoration-color: rgba(255, 255, 255, 0.6);
      }

      /* Notification with thumbnail */
      #quixel-download-notification .notification-content-with-thumb {
        display: flex;
        align-items: center;
        gap: 12px;
      }

      #quixel-download-notification .notification-thumbnail {
        width: 48px;
        height: 48px;
        object-fit: cover;
        border-radius: 4px;
        flex-shrink: 0;
      }

      #quixel-download-notification .notification-text {
        flex: 1;
        min-width: 0;
      }

      /* Animated dots for "Importing..." */
      @keyframes dotAnimation {
        0%, 20% { content: '.'; }
        40% { content: '..'; }
        60%, 100% { content: '...'; }
      }

      .animated-dots::after {
        content: '...';
        animation: dotAnimation 1.5s infinite;
      }
    \`;
    document.head.appendChild(styleElement);
  `;
};

