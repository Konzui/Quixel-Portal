// Quixel Injector - Main entry point for Quixel website injection
// Combines all Quixel-specific modules in the correct order

const quixelAuth = require('./quixel-auth');
const quixelButtons = require('./quixel-buttons');
const quixelPopups = require('./quixel-popups');
const quixelStyles = require('./quixel-styles');

module.exports = function() {
  // Combine all Quixel modules in initialization order
  return `
    // ═══════════════════════════════════════════════════════════════
    // 🎯 QUIXEL INJECTOR - Main entry point for Quixel website
    // ═══════════════════════════════════════════════════════════════
    
    ${quixelStyles()}
    ${quixelPopups()}
    ${quixelAuth()}
    ${quixelButtons()}
  `;
};

