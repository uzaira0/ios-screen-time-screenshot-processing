# Screenshot Processor - User Guide

## Welcome

Screenshot Processor is a powerful tool for extracting and managing hourly usage data from iPhone Battery and Screen Time screenshots. Whether you want fast server-based processing or complete offline privacy, we've got you covered.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Choosing Your Mode](#choosing-your-mode)
3. [Uploading Screenshots](#uploading-screenshots)
4. [Selecting the Grid](#selecting-the-grid)
5. [Reviewing Data](#reviewing-data)
6. [Exporting Data](#exporting-data)
7. [Keyboard Shortcuts](#keyboard-shortcuts)
8. [Troubleshooting](#troubleshooting)

---

## Getting Started

### First Time Setup

1. **Open the app** in your web browser
2. **Choose your processing mode** (Server or Local)
3. **Complete the onboarding tutorial** (optional but recommended)
4. **Start uploading screenshots!**

### System Requirements

**For Server Mode:**
- Modern web browser (Chrome 90+, Firefox 88+, Safari 15+)
- Internet connection
- Backend server running

**For Local Mode (WASM):**
- Modern web browser with WebAssembly support
- 4GB+ RAM recommended
- Works 100% offline after first load

---

## Choosing Your Mode

Screenshot Processor offers two processing modes:

### Server Mode 🖥️

**Best for:**
- Faster processing (GPU acceleration)
- Team collaboration
- Centralized data management
- Real-time consensus features

**Requires:**
- Active internet connection
- Backend server access

**Data Storage:** Server database

### Local Mode (WASM) 💻

**Best for:**
- Complete privacy
- Offline usage
- No server required
- Single-user scenarios

**Requires:**
- Modern browser only

**Data Storage:** Your device (IndexedDB)

### Switching Modes

1. Click the **Settings** icon (⚙️)
2. Select **Processing Mode**
3. Choose **Server** or **Local** mode
4. Confirm the change
5. App will reload with new mode

**Note:** Your data remains accessible in both modes.

---

## Uploading Screenshots

### Supported Screenshot Types

1. **Battery Usage** - iPhone battery usage graphs showing hourly battery drain
2. **Screen Time** - iPhone screen time graphs showing hourly app usage

### How to Upload

**Method 1: Drag and Drop**
1. Take screenshots on your iPhone
2. Transfer to your computer
3. Drag files onto the upload zone
4. Wait for processing to complete

**Method 2: Browse Files**
1. Click **Upload Screenshots** button
2. Browse to select files
3. Choose one or multiple screenshots
4. Click **Open** to upload

**Method 3: Keyboard Shortcut**
- Press `Ctrl/Cmd + U` to open upload dialog

### Upload Tips

✅ **Do:**
- Upload clear, high-quality screenshots
- Use the latest iOS screenshot format
- Upload multiple screenshots at once
- Ensure 24-hour grid is visible

❌ **Don't:**
- Upload cropped or edited screenshots
- Upload screenshots with low contrast
- Upload non-iPhone screenshots
- Mix different screenshot types

---

## Selecting the Grid

After uploading, you'll need to select the 24-hour usage grid.

### Auto-Detection

The app automatically tries to detect the grid boundaries using OCR. If successful:
- Grid corners are highlighted
- You can proceed to review data

### Manual Selection

If auto-detection fails or you want more precision:

1. Click **Select Grid Manually**
2. Click on the **top-left corner** of the 12 AM column
3. Click on the **top-right corner** of the 11 PM column
4. Click on the **bottom-left corner** (60-minute mark)
5. Click on the **bottom-right corner**
6. Review the selection
7. Click **Confirm** when satisfied

### Selection Tips

- **Zoom in** for better precision (`+ / -` keys)
- **Use crosshairs** that appear on hover
- **Look for anchor text**: "12", "2A", "AM" (left), "60" (right)
- **Grid lines** should be clearly visible
- **Dark mode**: App auto-converts dark screenshots

---

## Reviewing Data

After grid selection, review the extracted data:

### Data Display

- **Title**: App name (Screen Time) or date (Battery)
- **Total Usage**: OCR-extracted total
- **Hourly Values**: 24 columns showing usage per hour
- **Graph Overlay**: Visual representation

### Editing Values

**To edit a single value:**
1. Click the value cell
2. Type new value
3. Press `Enter` or click outside

**To edit multiple values:**
1. Select first cell
2. Use `Tab` or `Arrow Keys` to navigate
3. Enter values
4. Press `Ctrl/Cmd + S` to save

### Data Validation

The app automatically validates:
- ✅ Values are between 0-60 minutes
- ✅ Total matches sum of hourly values (±2 minutes tolerance)
- ⚠️ Warnings for discrepancies
- ❌ Errors for invalid data

---

## Exporting Data

### Export Formats

#### 1. CSV (Comma-Separated Values)

**Best for:**
- Excel analysis
- Simple data viewing
- Compatibility

**Contains:**
- Hourly usage data
- Metadata (date, app name)
- Annotations

**How to export:**
1. Click **Export** button
2. Select **CSV** format
3. Choose scope (current or all)
4. Click **Export**

#### 2. Excel (XLSX)

**Best for:**
- Professional reports
- Multiple sheets
- Advanced analysis

**Contains:**
- Annotations sheet
- Screenshots sheet
- Formatted tables

**How to export:**
1. Click **Export** button
2. Select **Excel** format
3. Choose scope
4. Click **Export**

#### 3. JSON (Complete Database)

**Best for:**
- Advanced users
- Complete data export
- Technical analysis

**Contains:**
- All database tables
- Complete metadata
- Raw data structures

**How to export:**
1. Click **Export** button
2. Select **JSON** format
3. Click **Export**

#### 4. Backup (Full Backup)

**Best for:**
- Data migration
- Disaster recovery
- Device switching

**Contains:**
- All screenshots
- All annotations
- All settings
- Complete database

**How to create backup:**
1. Click **Export** button
2. Select **Backup** format
3. Click **Export**
4. Save file securely

### Restoring Backups

1. Click **Import** button
2. Select backup file (.json)
3. Choose options:
   - **Merge**: Keep existing data
   - **Replace**: Clear existing data first
4. Click **Import**
5. Wait for completion

**Warning:** Replacing will permanently delete existing data!

---

## Keyboard Shortcuts

### General

| Shortcut | Action |
|----------|--------|
| `Ctrl/Cmd + K` | Show keyboard shortcuts |
| `Ctrl/Cmd + S` | Save current annotation |
| `Ctrl/Cmd + E` | Export data |
| `Ctrl/Cmd + U` | Upload screenshot |
| `Escape` | Close dialog or cancel |

### Navigation

| Shortcut | Action |
|----------|--------|
| `Tab` | Move to next field |
| `Shift + Tab` | Move to previous field |
| `Enter` | Confirm or submit |
| `Arrow Keys` | Navigate grid cells |

### Editing

| Shortcut | Action |
|----------|--------|
| `Ctrl/Cmd + Z` | Undo last change |
| `Ctrl/Cmd + Shift + Z` | Redo last change |
| `Ctrl/Cmd + A` | Select all |
| `Delete` | Clear selected value |

### Grid Selection

| Shortcut | Action |
|----------|--------|
| `Click + Drag` | Select grid corners |
| `+ / -` | Zoom in/out |
| `Space` | Toggle zoom mode |

---

## Troubleshooting

### Upload Issues

**Problem:** Screenshots won't upload

**Solutions:**
- Check file format (PNG, JPEG supported)
- Check file size (< 10MB recommended)
- Try uploading one at a time
- Clear browser cache
- Check internet connection (Server mode)

### Processing Issues

**Problem:** Processing takes too long

**Solutions:**
- **Server mode**: Check server connection
- **Local mode**: Close other browser tabs
- Clear browser cache
- Try smaller screenshots
- Use Server mode for faster processing

**Problem:** Inaccurate results

**Solutions:**
- Use manual grid selection
- Ensure screenshot quality is good
- Check for good contrast
- Verify correct screenshot type selected
- Try adjusting zoom level

### Grid Detection Issues

**Problem:** Auto-detection fails

**Solutions:**
- Use manual grid selection
- Ensure 24-hour grid is visible
- Check for anchor text ("12", "60")
- Verify screenshot isn't cropped
- Try different screenshot

### Data Issues

**Problem:** Exported data is incorrect

**Solutions:**
- Review data before exporting
- Check for validation errors
- Verify hourly values
- Re-process if needed
- Contact support if persistent

### Offline Issues

**Problem:** App doesn't work offline

**Solutions:**
- First load requires internet (downloads assets)
- Clear browser cache and reload
- Check browser compatibility
- Ensure Service Worker is registered
- Try installing as PWA

---

## Tips & Best Practices

### For Best Results

1. **Use high-quality screenshots**
   - Clear, uncompressed images
   - Good contrast between bars and background
   - Full 24-hour grid visible

2. **Organize your workflow**
   - Process similar screenshots together
   - Use consistent naming
   - Export regularly

3. **Leverage keyboard shortcuts**
   - Faster workflow
   - Less mouse clicking
   - Learn 5-10 most common shortcuts

4. **Regular backups**
   - Export backups monthly
   - Store in multiple locations
   - Test restore process

5. **Choose the right mode**
   - Server mode for collaboration
   - Local mode for privacy
   - Consider your needs

### Data Management

- **Export frequently** to avoid data loss
- **Verify data** before deleting screenshots
- **Use descriptive filenames** for exports
- **Keep backups** in cloud storage
- **Document your process** for consistency

---

## Getting Help

### Resources

- **FAQ**: See FAQ.md for common questions
- **Privacy Policy**: See privacy-policy.md
- **GitHub Issues**: Report bugs
- **Keyboard Shortcuts**: Press `Ctrl/Cmd + K` in app

### Support

For technical support:
1. Check this guide first
2. Review FAQ
3. Search GitHub issues
4. Create new issue with details

Include in support requests:
- Browser version
- Processing mode (Server/Local)
- Steps to reproduce
- Screenshot of error (if applicable)

---

## What's Next?

Now that you know the basics:

1. **Try both processing modes** to see which you prefer
2. **Process your first screenshot** end-to-end
3. **Export your data** to your preferred format
4. **Explore keyboard shortcuts** for efficiency
5. **Set up regular backups** for peace of mind

**Happy processing!** 🎉
