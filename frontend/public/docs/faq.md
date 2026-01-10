# Frequently Asked Questions (FAQ)

## General Questions

### What is Screenshot Processor?

Screenshot Processor is a web application that extracts hourly usage data from iPhone Battery and Screen Time screenshots. It uses OCR (Optical Character Recognition) and image processing to automatically read the bar graphs and convert them into structured data you can export.

### Do I need to install anything?

No installation required! Screenshot Processor runs entirely in your web browser. However, you can install it as a Progressive Web App (PWA) for a more app-like experience and offline access.

### Is it free?

Yes, Screenshot Processor is completely free and open source.

---

## Processing Modes

### What's the difference between Server Mode and Local Mode?

**Server Mode:**
- Processes screenshots on a backend server
- Faster processing with GPU acceleration
- Requires internet connection
- Data stored on server
- Supports team collaboration

**Local Mode (WASM):**
- Processes screenshots in your browser
- 100% offline after first load
- Complete privacy - data never leaves your device
- No server required
- Single-user only

### Which mode should I use?

**Use Server Mode if:**
- You want fastest processing
- You need collaboration features
- You have reliable internet
- You don't mind server storage

**Use Local Mode if:**
- Privacy is your top priority
- You work offline frequently
- You don't have server access
- You want complete control of your data

### Can I switch between modes?

Yes! You can switch modes anytime from Settings. Your data remains accessible in both modes.

### Does switching modes delete my data?

No. Data is preserved when switching modes. However:
- Server mode data stays on the server
- Local mode data stays in your browser
- They don't automatically sync

---

## Data & Privacy

### Where is my data stored?

**Server Mode:**
- Screenshots and annotations stored in server database
- Processed on server backend
- Accessible from any device with login

**Local Mode:**
- All data stored in your browser's IndexedDB
- Never transmitted to any server
- Accessible only on this device/browser

### Is my data private?

**Server Mode:**
- Data stored on server you're connected to
- Access controlled by authentication
- Subject to server's privacy policy

**Local Mode:**
- Complete privacy
- Data never leaves your device
- No tracking, no analytics
- No server communication

### Can I export my data?

Yes! Export to:
- **CSV**: Simple spreadsheet format
- **Excel**: Professional format with multiple sheets
- **JSON**: Complete database export
- **Backup**: Full backup for migration/recovery

### How do I backup my data?

1. Click Export button
2. Select "Backup" format
3. Save the file securely
4. Store in multiple locations (cloud, external drive)

We recommend monthly backups.

### Can I delete my data?

**Server Mode:**
- Contact server administrator
- Or delete from your account settings

**Local Mode:**
- Settings → Clear All Data
- Or clear browser data (IndexedDB)

**Warning:** Deletion is permanent! Export backups first.

---

## Technical Questions

### What browsers are supported?

**Minimum versions:**
- Chrome 90+
- Firefox 88+
- Safari 15+
- Edge 90+

**Not supported:**
- Internet Explorer
- Old mobile browsers
- Browsers without WebAssembly (for Local Mode)

### Does it work on mobile?

Yes! The app is responsive and works on mobile browsers. However:
- Larger screens recommended for grid selection
- Desktop processing is faster
- Touch controls may be less precise

You can also install as a PWA for better mobile experience.

### What is a PWA?

Progressive Web App - a web app that behaves like a native app:
- Install on home screen
- Works offline
- Fast loading
- App-like experience

### How do I install as PWA?

**Desktop (Chrome/Edge):**
1. Click install icon in address bar
2. Or Settings → Install Screenshot Processor

**Mobile (Chrome):**
1. Tap menu (⋮)
2. Tap "Install app" or "Add to Home Screen"

**Mobile (Safari):**
1. Tap share button
2. Tap "Add to Home Screen"

### Does it work offline?

**Server Mode:**
- Requires internet connection
- Cannot process screenshots offline

**Local Mode:**
- Works 100% offline after first load
- All processing happens in browser
- No internet required

### How much storage does it use?

**Local Mode:**
- App files: ~15-20 MB (cached)
- Per screenshot: 2-5 MB
- Hourly data: < 1 KB each
- Total depends on your data

**Browser storage limits:**
- Chrome: ~60% of available disk
- Firefox: ~50% of available disk
- Safari: ~1 GB (can request more)

### What if I run out of storage?

1. Export old data
2. Delete processed screenshots
3. Clear browser cache
4. Use Server Mode instead

---

## Processing Questions

### What screenshot types are supported?

1. **iPhone Battery Usage** (Settings → Battery)
2. **iPhone Screen Time** (Settings → Screen Time)

Must show the 24-hour bar graph.

### Why isn't auto-detection working?

Common causes:
- Screenshot cropped or edited
- Poor image quality/contrast
- Grid not fully visible
- Unusual screenshot format

**Solution:** Use manual grid selection

### Why are my results inaccurate?

Possible reasons:
- Grid selection was imprecise
- Screenshot quality issues
- Bar colors too similar to background
- Grid lines not clear

**Solutions:**
- Use manual selection with zoom
- Try higher quality screenshots
- Ensure good contrast
- Verify correct grid boundaries

### How accurate is the extraction?

**Typical accuracy:**
- Within ±1 minute: 95% of hours
- Within ±2 minutes: 99% of hours
- Exact match: 70-80% of hours

Accuracy depends on screenshot quality and grid selection precision.

### Can I edit extracted values?

Yes! Click any value to edit. The app validates:
- Values between 0-60 minutes
- Total matches hourly sum
- Shows warnings for discrepancies

### Why does processing take so long?

**Server Mode:**
- Usually 2-5 seconds
- Check server connection
- Server may be busy

**Local Mode:**
- First run: 5-15 seconds (loading libraries)
- Subsequent: 3-10 seconds
- Depends on device performance
- Browser may throttle background tabs

---

## Export & Import

### What format should I export to?

**For Excel/Google Sheets:**
- Use CSV or Excel format
- Easy to open and analyze

**For backup:**
- Use Backup format
- Preserves everything

**For technical users:**
- Use JSON format
- Complete raw data

### Can I import my old data?

Yes! Import from:
- Previous JSON/Backup exports
- Other devices running the app

1. Click Import
2. Select backup file
3. Choose merge or replace
4. Wait for completion

### What's the difference between export scopes?

**Current Screenshot:**
- Only selected screenshot's data
- Smaller file size
- Quick export

**All Data:**
- All screenshots and annotations
- Complete dataset
- Recommended for backups

---

## Troubleshooting

### The app won't load

**Try:**
1. Hard refresh (Ctrl/Cmd + Shift + R)
2. Clear browser cache
3. Try different browser
4. Check browser console for errors
5. Disable browser extensions

### Screenshots won't upload

**Check:**
- File format (PNG/JPEG only)
- File size (< 10MB)
- Browser storage quota
- Internet connection (Server mode)

**Try:**
- Upload one at a time
- Use smaller files
- Clear space in browser
- Try different browser

### App is slow or freezing

**Causes:**
- Too many browser tabs open
- Low device memory
- Large screenshots
- Old device/browser

**Solutions:**
- Close other tabs
- Use Server mode
- Reduce screenshot size
- Use desktop instead of mobile
- Clear browser data

### Data disappeared

**Server Mode:**
- Check if logged in
- Verify correct server
- Contact administrator

**Local Mode:**
- Browser data cleared?
- Different browser/device?
- Restore from backup

**Prevention:**
- Export backups regularly
- Don't clear browser data
- Use Server mode for persistence

### Export/Import failed

**Common causes:**
- Corrupted file
- Insufficient storage
- Browser compatibility
- Large file size

**Solutions:**
- Try smaller exports
- Use different format
- Clear browser space
- Try different browser

---

## Performance

### How can I speed up processing?

1. **Use Server Mode** (much faster)
2. **Close other tabs** to free memory
3. **Use smaller screenshots** (resize to 1920x1080)
4. **Upgrade device** if very old
5. **Use desktop** instead of mobile

### Why is memory usage high?

**Normal:**
- OpenCV.js uses 30-50 MB
- Image processing is memory-intensive
- Temporary spike during processing

**Concerning:**
- Constant growth
- > 500 MB usage
- Browser crashes

**Solutions:**
- Restart browser periodically
- Process in batches
- Use Server mode
- Report if persistent

### Can I process multiple screenshots at once?

**Currently:**
- Upload multiple (queued)
- Process one at a time
- Sequential processing

**Future:**
- Batch processing planned
- Parallel workers considered

---

## Security

### Is it safe to use?

Yes, Screenshot Processor is:
- Open source (auditable)
- No tracking or analytics
- No ads or monetization
- Privacy-focused

### Does it collect any data?

**Local Mode:**
- Zero data collection
- No analytics
- No server communication
- Completely private

**Server Mode:**
- Only what you upload
- Controlled by server admin
- Check server's privacy policy

### Can others see my data?

**Local Mode:**
- No - data only on your device
- Not accessible to anyone

**Server Mode:**
- Only if server is compromised
- Or if you share your account
- Use strong passwords
- Enable 2FA if available

### Should I clear my data?

**Clear when:**
- Sharing/selling device
- Using public computer
- No longer need data

**Don't clear if:**
- You haven't backed up
- You're still using the app
- You want to keep history

---

## Advanced

### Can I automate processing?

Not currently supported, but possible future features:
- API access
- Batch processing
- CLI tool

### Can I customize the app?

Yes! It's open source:
- Fork the repository
- Modify to your needs
- Self-host your own version

### Does it support other screenshot types?

Currently only iPhone Battery and Screen Time screenshots. Support for other types (Android, fitness apps, etc.) may be added in future.

### Can I contribute?

Yes! Contributions welcome:
- Report bugs (GitHub Issues)
- Suggest features
- Submit pull requests
- Improve documentation
- Translate to other languages

---

## Getting More Help

### Still have questions?

1. **Check User Guide** - Comprehensive documentation
2. **Search GitHub Issues** - See if already asked
3. **Create New Issue** - Provide details:
   - Browser/OS version
   - Processing mode
   - Steps to reproduce
   - Screenshots of error

### Found a bug?

Report on GitHub with:
- Clear description
- Steps to reproduce
- Expected vs actual behavior
- Browser console errors
- Screenshots if applicable

### Want a feature?

Submit feature request on GitHub:
- Describe the feature
- Explain use case
- Note similar apps if any
- Estimate priority

---

**Last updated:** November 2025
