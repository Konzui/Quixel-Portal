// Injector Coordinator - Main coordinator that loads and combines all modules
// Takes website name as parameter and returns combined injection script

const fs = require('fs');
const path = require('path');

// Base modules (loaded for all websites)
const baseInjector = require('./base/base-injector');
const errorHandler = require('./base/error-handler');
const notificationSystem = require('./base/notification-system');
const progressBar = require('./base/progress-bar');
const communicationBridge = require('./base/communication-bridge');

// Utility modules
const domUtils = require('./utils/dom-utils');
const urlUtils = require('./utils/url-utils');
const assetUtils = require('./utils/asset-utils');

// Website-specific injectors
const quixelInjector = require('./websites/quixel/quixel-injector');
const polyhavenInjector = require('./websites/polyhaven/polyhaven-injector');

/**
 * Generate injection script for a specific website
 * @param {string} website - Website identifier ('quixel', 'polyhaven', etc.)
 * @returns {string} Combined JavaScript code as string
 */
function generateInjectionScript(website) {
  // Start with IIFE wrapper
  let script = `
    (function() {
      // ═══════════════════════════════════════════════════════════════
      // 🚀 PORTAL INJECTOR - Website: ${website}
      // ═══════════════════════════════════════════════════════════════
  `;

  // Load base modules (common to all websites)
  script += communicationBridge();
  script += errorHandler();
  script += baseInjector();
  script += progressBar();
  script += notificationSystem();

  // Load utility modules
  script += domUtils();
  script += urlUtils();
  script += assetUtils();

  // Load website-specific modules
  switch (website) {
    case 'quixel':
      script += quixelInjector();
      break;
    case 'polyhaven':
      script += polyhavenInjector();
      break;
    default:
      console.warn(`Unknown website: ${website}, using base modules only`);
  }

  // Close IIFE
  script += `
    })();
  `;

  return script;
}

module.exports = generateInjectionScript;

