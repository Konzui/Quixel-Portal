# Assets Directory

Place your custom assets here:

## Folder Structure

```
assets/
├── icons/          # SVG icons for the UI
│   ├── logo.svg   # Main application logo
│   ├── back.svg   # Custom back button icon
│   ├── forward.svg # Custom forward button icon
│   └── ...        # Other custom icons
└── images/         # Other images (PNG, JPG, etc.)
```

## Using Custom SVG Icons

### Method 1: Inline SVG (Current approach)
Replace the inline SVG in `titlebar.html` with your custom SVG code.

### Method 2: External SVG Files
1. Place your SVG files in `assets/icons/`
2. Reference them in HTML:
   ```html
   <img src="assets/icons/logo.svg" alt="Logo">
   ```

### Method 3: CSS Background
1. Place your SVG files in `assets/icons/`
2. Reference them in CSS:
   ```css
   .logo-icon {
     background-image: url('../assets/icons/logo.svg');
   }
   ```

### Method 4: Load SVG dynamically with JavaScript
```javascript
fetch('assets/icons/logo.svg')
  .then(response => response.text())
  .then(svgContent => {
    document.getElementById('logo-container').innerHTML = svgContent;
  });
```

## Icon Requirements

- **Format**: SVG (recommended for scalability)
- **Size**: Icons should be designed for 20x20px or 24x24px viewBox
- **Color**: Use `currentColor` for stroke/fill to allow dynamic theming
- **Optimization**: Minimize SVG code for best performance

## Example SVG with currentColor

```svg
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M12 2L2 7v10c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V7l-10-5z"
        fill="currentColor"/>
</svg>
```

This allows the icon to inherit the color from CSS, making theming easier.
