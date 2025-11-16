# Quixel Portal Debug Tool Guide

## Overview

This debug tool helps you understand exactly **when** and **how** to inject JavaScript code into the Megascans website to modify the download button. It tracks all relevant events, detects popups, monitors URL changes, and automatically finds download buttons.

---

## Features

### 🔍 Visual Debug Overlay
- **Green console** in the top-right corner of the page
- Real-time logging of all events
- Automatically appears when the app starts
- Shows the last 20 debug messages
- **Close button (✕)** in the top-right corner of the overlay
- **Toggle button (🔍)** appears when overlay is closed - click to reopen

### 📊 What It Tracks

1. **URL Changes** - Detects when you navigate or when query parameters change (like `?assetId=xglxdjr`)
2. **Asset Details** - Automatically detects when an asset detail popup opens
3. **DOM Mutations** - Monitors when new elements (popups/modals) are added to the page
4. **Download Buttons** - Searches for and highlights download buttons in RED
5. **Button Properties** - Logs button text, classes, IDs, and HTML tags

---

## How to Use

### Step 1: Start the Application

```bash
cd electron_app
npm start
```

The debug overlay will automatically appear in the top-right corner with a green border.

### Step 2: Navigate to Megascans

The app will load `https://quixel.com/megascans/home` automatically. The debug console will show:
- ✅ "Debug system initialized"
- 👂 "Monitoring URL changes and DOM mutations..."

### Step 3: Click on an Asset Card

When you click on an asset card:

1. **The URL changes** from `https://quixel.com/megascans/home` to `https://quixel.com/megascans/home?assetId=xglxdjr`
2. **The debug overlay will log:**
   - 🔄 "URL changed: https://..."
   - 🎯 "ASSET DETAIL DETECTED! ID: xglxdjr"
   - 🔍 "Searching for download button..."

3. **If a popup/modal appears:**
   - 🪟 "POPUP/MODAL DETECTED!"
   - Modal classes will be logged

4. **Download buttons will be found:**
   - ✅ "Found X potential download button(s)!"
   - Buttons will be **highlighted with a RED outline**
   - Button details will be logged:
     - Tag name (e.g., `<button>`, `<a>`)
     - Text content
     - CSS classes
     - ID attribute

### Step 4: Inspect the Found Buttons

The debug tool provides several ways to inspect buttons:

#### Method 1: Visual Inspection
All download buttons are highlighted with a **red outline** on the page.

#### Method 2: Console Access
Open the browser console (F12) and access found buttons:

```javascript
// View all found buttons
window.downloadButtons

// Access a specific button (0-indexed)
window.downloadButtons[0]

// Test changing the button color to blue
window.testButtonColorChange(0)  // Changes button #0 to blue
window.testButtonColorChange(1)  // Changes button #1 to blue
```

#### Method 3: Debug Overlay Logs
The debug overlay shows detailed information about each button found, including:
- Button number
- HTML tag
- Text content
- CSS class names
- ID attribute

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| **F9** | Toggle debug overlay on/off |
| **F10** | Manually trigger download button search |
| **F12** | Toggle browser DevTools |

## Closing and Opening the Debug Console

### Method 1: Close Button
- Click the **✕** button in the top-right corner of the debug overlay
- A small **🔍** toggle button will appear in the same position
- Click the **🔍** button to reopen the debug overlay

### Method 2: Keyboard Shortcut
- Press **F9** to toggle the debug overlay on/off
- Works whether the overlay is open or closed

### Method 3: Developer Menu
- Click on the menu → **Developer** → **Toggle Debug Overlay**

---

## Understanding the Console Output

### Main Process (Terminal/Console)
You'll see logs like:
```
🔵 [DEBUG] Navigation started: https://...
✅ [DEBUG] Page loaded: https://...
📄 [DEBUG] Page title updated: Megascans
🔄 [DEBUG] In-page navigation (URL changed): https://...?assetId=xglxdjr
🎯 [DEBUG] Asset detail opened! Asset ID: xglxdjr
✅ [MAIN] Debug script injected successfully
```

### Browser Console (F12)
You'll see logs like:
```
🚀 [INJECTION] Debug script loaded at: 2025-01-15T...
📍 [INJECTION] Current URL: https://...
[DEBUG] Debug system initialized
[DEBUG] URL changed: https://...?assetId=xglxdjr
[DEBUG] 🎯 ASSET DETAIL DETECTED! ID: xglxdjr
[DEBUG] 🔍 Searching for download button...
[DEBUG] Strategy 1 found 2 button(s)
[DEBUG] ✅ Found 2 potential download button(s)!
[DEBUG] Button #1: <BUTTON> "Download" (class="btn-primary download-btn", id="")
```

### Debug Overlay (On-Page)
Real-time visual feedback in the green console overlay showing all events as they happen.

---

## Testing Button Color Change

Once buttons are found, test the color change:

### Method 1: Use the Helper Function (Easiest)
Open browser console (F12):
```javascript
// Change first button to blue
window.testButtonColorChange(0)

// If there are multiple buttons, try the others
window.testButtonColorChange(1)
window.testButtonColorChange(2)
```

### Method 2: Manual JavaScript
```javascript
// Change background to blue
window.downloadButtons[0].style.backgroundColor = 'blue';
window.downloadButtons[0].style.color = 'white';

// Change border
window.downloadButtons[0].style.border = '3px solid blue';
```

---

## Search Strategies Explained

The debug tool uses **3 different strategies** to find download buttons:

### Strategy 1: Text-Based Search
Looks for buttons containing text like:
- "download"
- "export"

### Strategy 2: HTML-Based Search
Looks for buttons with:
- Download-related HTML content
- Icons (SVG elements)
- Arrow icons

### Strategy 3: Container-Based Search
Searches specifically in:
- `[role="dialog"]` elements
- `.modal` elements
- `[class*="modal"]` elements
- `[class*="dialog"]` elements
- `[class*="popup"]` elements

---

## Key Events to Listen For

Based on your requirement, here are the **optimal events** to use for injection:

### ✅ Recommended: `did-navigate-in-page` Event
**When:** URL changes from `home` to `home?assetId=xyz`
**Why:** This fires immediately when the asset detail opens
**Code location:** `main.js:80-95`

```javascript
browserView.webContents.on('did-navigate-in-page', (event, url, isMainFrame) => {
  if (isMainFrame && url.includes('assetId=')) {
    // Inject your code here!
    setTimeout(() => {
      injectDownloadButtonDebug();
    }, 500);
  }
});
```

### Alternative: DOM Mutation Observer
**When:** New modal/popup elements are added to the page
**Why:** Catches dynamically created popups
**Code location:** Inside the injected script `main.js:165-192`

```javascript
const domObserver = new MutationObserver((mutations) => {
  // Detects when modals appear
  if (isModal) {
    // Inject your code here!
  }
});
```

---

## Production Implementation

Once you've identified the correct button selector, here's how to implement the actual injection:

### Step 1: Modify the Injection Function

In `main.js`, update the `injectDownloadButtonDebug()` function:

```javascript
function injectDownloadButtonDebug() {
  if (!browserView) return;

  const script = `
    (function() {
      // Wait for the button to appear
      setTimeout(() => {
        // Replace this selector with what you found via debugging!
        const downloadBtn = document.querySelector('REPLACE_WITH_YOUR_SELECTOR');

        if (downloadBtn) {
          // Change background to blue
          downloadBtn.style.backgroundColor = 'blue';
          downloadBtn.style.color = 'white';

          console.log('✅ Download button modified!');
        } else {
          console.log('❌ Download button not found');
        }
      }, 1000);
    })();
  `;

  browserView.webContents.executeJavaScript(script);
}
```

### Step 2: Disable Debug Mode

Once you're ready for production:

1. **Remove the debug overlay injection** - Comment out the `injectDebugScript()` call in `main.js:71`
2. **Remove console logs** - Comment out the `console.log()` statements
3. **Keep the event listener** - Keep the `did-navigate-in-page` event to detect asset details

---

## Troubleshooting

### Debug overlay doesn't appear
- Look for the **🔍** toggle button in the top-right corner - click it to open
- Press **F9** to toggle visibility
- Check browser console (F12) for errors
- Reload the page (Ctrl+R)

### No buttons found
- The popup might take longer to load - press **F10** to manually search
- Try different timings in the `setTimeout` (increase from 500ms to 1000ms or 2000ms)
- Check if the website uses a different structure

### Buttons found but wrong ones
- Check the debug logs to see which buttons were found
- Use the browser console to inspect `window.downloadButtons` array
- Refine your selector based on the logged class names and IDs

### Button color doesn't change
- Make sure you're targeting the right button index
- Some buttons might have `!important` CSS rules - use `style.setProperty('background-color', 'blue', 'important')`
- Check if the button is inside a shadow DOM (requires different approach)

---

## Example Workflow

Here's a complete workflow example:

1. **Start app** → Debug overlay appears ✅
2. **Click asset card** → URL changes to `?assetId=xyz` 🔄
3. **Debug overlay logs** → "ASSET DETAIL DETECTED!" 🎯
4. **Popup appears** → "POPUP/MODAL DETECTED!" 🪟
5. **Buttons found** → RED outlines appear ✅
6. **Check console** → See button details 📊
7. **Test color** → `window.testButtonColorChange(0)` 🎨
8. **Button turns blue** → Success! ✅
9. **Copy selector** → Use in production code 📋

---

## Next Steps

1. ✅ Run the app and click on an asset
2. ✅ Observe the debug console logs
3. ✅ Note which buttons are found and their properties
4. ✅ Test the color change with `window.testButtonColorChange(0)`
5. ✅ Identify the correct selector (class, ID, or text content)
6. ✅ Implement the production injection code
7. ✅ Disable debug mode for production

---

## Questions?

If you need help with:
- Specific button selectors
- Timing issues
- Different website structures
- Advanced injection techniques

Feel free to ask! The debug tool provides all the information you need to make informed decisions about when and how to inject your code.
