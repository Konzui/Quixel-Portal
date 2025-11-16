# Element Inspector Tool Guide

## Overview

The Element Inspector is a powerful debugging tool that allows you to click on any element on the Megascans website and get comprehensive information about it, including CSS selectors, computed styles, attributes, and more.

---

## How to Use

### Activating the Element Inspector

There are two ways to enable the Element Inspector:

**Method 1: Menu (Recommended)**
1. Click on the **logo/menu** in your custom titlebar
2. Navigate to **Developer** → **Element Inspector**

**Method 2: Keyboard Shortcut**
- Press **F9**

### Using the Element Inspector

Once enabled, you'll see a message in the browser console:
```
🔍 Element Inspector ENABLED - Click on any element to inspect it
💡 Click on the logo menu > Developer > Element Inspector again to disable
```

**How it works:**
1. **Hover** over any element → Orange outline appears (#ff6600)
2. **Click** on the element → Detailed information is logged to the console
3. **Green flash** → The clicked element briefly flashes green for confirmation

### Disabling the Element Inspector

To turn off the inspector:
- Click **Developer** → **Element Inspector** again (or press **F9**)
- Console will show: `🔍 Element Inspector DISABLED`

---

## Information Provided

When you click on an element, the inspector logs comprehensive information:

### 📋 Basic Info
- **Tag**: HTML tag name (e.g., `BUTTON`, `DIV`, `A`)
- **ID**: Element ID attribute (or "(none)")
- **Classes**: All CSS classes applied to the element
- **Text**: Text content (first 100 characters)

### 🎯 CSS Selector
- **Selector**: Optimized CSS selector you can use to target this element
  - Uses ID if available (e.g., `#submit-button`)
  - Falls back to classes (e.g., `button.Button___1mkoh.Button--fullWidth___2subI`)
  - Uses tag name as fallback (e.g., `button`)

### 📐 Attributes
- Table showing **all HTML attributes** on the element
- Includes data attributes, ARIA attributes, etc.

### 🎨 Computed Styles
- Table showing the **final computed CSS values** for:
  - Layout: `display`, `position`, `width`, `height`
  - Colors: `background`, `background-color`, `color`
  - Spacing: `border`, `padding`, `margin`
  - Typography: `font-family`, `font-size`, `font-weight`
  - Others: `z-index`, `opacity`, `cursor`

### 📍 Position & Size
- **X**: Horizontal position from viewport left
- **Y**: Vertical position from viewport top
- **Width**: Element width in pixels
- **Height**: Element height in pixels

### 📄 HTML
- First 200 characters of the element's `innerHTML`

### 💻 Element Object
- The raw DOM element object (expandable in console)

---

## Example Output

```
🔍 ELEMENT INSPECTOR RESULTS
═══════════════════════════════════════
📋 BASIC INFO
Tag:         BUTTON
ID:          (none)
Classes:     Button___1mkoh Button--fullWidth___2subI
Text:        Download

🎯 CSS SELECTOR
Selector:    button.Button___1mkoh.Button--fullWidth___2subI

📐 ATTRIBUTES
┌─────────┬────────────────────────────────────┐
│ (index) │ Value                              │
├─────────┼────────────────────────────────────┤
│ class   │ 'Button___1mkoh Button--fullWidth' │
│ type    │ 'button'                           │
└─────────┴────────────────────────────────────┘

🎨 COMPUTED STYLES
┌────────────────┬─────────────────────┐
│ (index)        │ Value               │
├────────────────┼─────────────────────┤
│ display        │ 'block'             │
│ position       │ 'relative'          │
│ width          │ '200px'             │
│ height         │ '40px'              │
│ background     │ 'rgb(12, 140, 233)' │
│ color          │ 'rgb(255, 255, 255)'│
│ border         │ 'none'              │
│ padding        │ '10px 20px'         │
│ font-size      │ '14px'              │
│ cursor         │ 'pointer'           │
└────────────────┴─────────────────────┘

📍 POSITION & SIZE
X:           150
Y:           450
Width:       200
Height:      40

📄 HTML (first 200 chars)
Download

💻 ELEMENT OBJECT
▶ button.Button___1mkoh.Button--fullWidth___2subI
═══════════════════════════════════════
```

---

## Use Cases

### 1. Finding the Right CSS Selector
**Problem**: You want to modify an element but don't know its selector.

**Solution**:
1. Enable Element Inspector
2. Click on the element
3. Look at "🎯 CSS SELECTOR" in the output
4. Use that selector in your injection code

### 2. Understanding Element Styling
**Problem**: An element looks different than expected, and you need to know why.

**Solution**:
1. Inspect the element
2. Check "🎨 COMPUTED STYLES" to see the final CSS values
3. Identify which styles are being applied

### 3. Getting Attribute Information
**Problem**: You need to know what data attributes or ARIA attributes an element has.

**Solution**:
1. Inspect the element
2. Look at "📐 ATTRIBUTES" table
3. See all attributes and their values

### 4. Determining Element Position
**Problem**: You need to position something relative to an element.

**Solution**:
1. Inspect the element
2. Check "📍 POSITION & SIZE"
3. Use the coordinates for positioning

### 5. Modifying Download Button Example
**Real Example**:
```javascript
// 1. Enable Inspector and click on download button
// 2. You see: Selector: button.Button___1mkoh.Button--fullWidth___2subI
// 3. Use it in your CSS injection:

button.Button___1mkoh.Button--fullWidth___2subI {
  background: #0C8CE9 !important;
  color: white !important;
}
```

---

## Tips & Tricks

### Tip 1: Use Console Groups
The inspector uses `console.group()` to organize information. You can collapse/expand groups in the DevTools console.

### Tip 2: Inspect Multiple Elements
You can click on multiple elements in succession. Each inspection is logged separately, making it easy to compare elements.

### Tip 3: Check Nested Elements
If you click on a parent element by mistake, just click on a child element. The orange hover outline helps you target precisely.

### Tip 4: Copy Selector from Console
You can right-click on the selector in the console and copy it for use in your code.

### Tip 5: Combine with DevTools
Use the Element Inspector alongside the browser DevTools (F12) for maximum debugging power:
- Inspector → Quick overview and selector
- DevTools → Deep dive into DOM structure and styles

---

## Visual Feedback

### Hover State
- **Orange outline** (`#ff6600`, 2px) appears when hovering over elements
- Helps you target the exact element you want to inspect

### Click Confirmation
- **Green outline** (`#00ff00`, 3px) flashes for 1 second after clicking
- Confirms your selection was registered

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| **F9** | Toggle Element Inspector on/off |
| **F12** | Open browser DevTools |

---

## Troubleshooting

### Inspector not working
- Make sure you see the "ENABLED" message in the console
- Try pressing F9 twice (disable then re-enable)
- Refresh the page and try again

### Can't click on certain elements
- Some elements might have event handlers that prevent inspection
- Try clicking on a parent or child element instead

### Orange outline not appearing
- Check if the element has `pointer-events: none` CSS
- Try hovering more slowly
- Disable and re-enable the inspector

### Too much information in console
- Use the console's filter feature to search for "ELEMENT INSPECTOR"
- Clear the console (Ctrl+L) before inspecting new elements

---

## Download Button Styling

The app automatically styles download buttons with:
- **Background**: `#0C8CE9` (blue)
- **Text Color**: `white`
- **Selector**: `button.Button___1mkoh.Button--fullWidth___2subI`

This styling happens **instantly** when buttons appear on the page thanks to CSS injection!

---

## Developer Notes

### How It Works

1. **Event Listeners**: Captures `click`, `mouseover`, and `mouseout` events
2. **Event Capture Phase**: Uses `addEventListener(..., true)` to catch events before they bubble
3. **Prevent Default**: Stops normal click behavior while inspector is active
4. **Computed Styles**: Uses `window.getComputedStyle()` to get final CSS values
5. **Auto-Toggle**: Clicking the menu item again disables the inspector

### Code Location

- **Main Function**: `enableElementInspector()` in `main.js:140-283`
- **Menu Item**: Developer menu in `main.js:610-616`
- **Keyboard Shortcut**: F9 accelerator

---

## Conclusion

The Element Inspector is your go-to tool for understanding the structure and styling of any element on the Megascans website. Use it to find selectors, debug styles, and gather information needed for custom modifications!

**Happy Inspecting! 🔍**
