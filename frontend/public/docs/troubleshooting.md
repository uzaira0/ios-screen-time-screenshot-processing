# Troubleshooting Guide

## Common Issues and Solutions

### App Won't Load

#### Symptoms
- Blank white screen
- Loading spinner forever
- Error message on startup

#### Solutions

1. **Check Internet Connection** (first load only)
   - Ensure stable connection
   - Try refreshing the page
   - Check if other sites load

2. **Clear Browser Cache**
   ```
   Chrome: Ctrl+Shift+Delete > Clear cached images and files
   Firefox: Ctrl+Shift+Delete > Cached Web Content
   Safari: Cmd+Option+E
   ```

3. **Try Incognito/Private Mode**
   - Rules out extension conflicts
   - Tests with clean slate

4. **Update Browser**
   - Ensure using latest version
   - Check browser compatibility

5. **Try Different Browser**
   - Test with Chrome, Firefox, or Edge
   - Verify WebAssembly support

### Service Worker Issues

#### Symptoms
- "New version available" loops
- Offline mode not working
- App doesn't update

#### Solutions

1. **Unregister Service Worker**
   - Open DevTools (F12)
   - Application tab > Service Workers
   - Click "Unregister"
   - Refresh page

2. **Hard Refresh**
   - Windows: Ctrl+Shift+R
   - Mac: Cmd+Shift+R

3. **Clear All Site Data**
   - DevTools > Application > Clear storage
   - Check all boxes
   - Click "Clear site data"

### WASM Module Loading Failures

#### Symptoms
- "Failed to load OpenCV"
- "Failed to load Tesseract"
- Processing doesn't start

#### Solutions

1. **Check Network Connection**
   - WASM modules load from CDN first time
   - Verify CDN access
   - Wait for complete download

2. **Clear Cache and Retry**
   - Clear browser cache
   - Reload app
   - Wait for modules to download

3. **Check Browser Console**
   - F12 > Console tab
   - Look for specific errors
   - Share error messages when seeking help

4. **Memory Issues**
   - Close unused tabs
   - Restart browser
   - Free up RAM

### Grid Detection Failures

#### Symptoms
- "Grid detection failed"
- Incorrect grid selection
- Missing grid overlay

#### Solutions

1. **Use Manual Selection**
   - Click "Manual Grid Selection"
   - Carefully select corners
   - Use zoom for precision

2. **Check Screenshot Quality**
   - Ensure full graph visible
   - Good lighting, not too dark
   - No partial crops
   - Proper orientation

3. **Retake Screenshot**
   - Better lighting
   - Full screen capture
   - Steady hand

4. **Try Different Screenshot**
   - Test with known good image
   - Isolate screenshot issue

### OCR Accuracy Issues

#### Symptoms
- Wrong numbers extracted
- Missing values
- Garbled text

#### Solutions

1. **Manual Grid Selection**
   - More accurate than auto-detection
   - Precise corner placement
   - Better OCR results

2. **Screenshot Quality**
   - High resolution
   - Good contrast
   - Clear, sharp image
   - Proper lighting

3. **Manual Correction**
   - Always review extracted values
   - Edit incorrect readings
   - Use reference screenshot

4. **Image Preprocessing**
   - App automatically adjusts contrast
   - Sometimes manual retry helps

### Export Issues

#### Symptoms
- Export button doesn't work
- Download doesn't start
- Corrupted export files

#### Solutions

1. **Check Popup Blocker**
   - Allow popups for this site
   - Temporarily disable blocker

2. **Disk Space**
   - Ensure sufficient free space
   - Check downloads folder

3. **Try Different Format**
   - If CSV fails, try Excel
   - JSON is most reliable

4. **Browser Permissions**
   - Grant download permissions
   - Check site settings

### Performance Issues

#### Symptoms
- Slow processing
- UI freezes
- High memory usage
- Browser crashes

#### Solutions

1. **Close Unused Tabs**
   - Free up memory
   - Reduce browser load

2. **Switch to Server Mode**
   - Much faster processing
   - Less memory intensive

3. **Clear Old Data**
   - Export and archive
   - Delete old screenshots
   - Compact database

4. **Reduce Image Size**
   - Large images take longer
   - Resize before upload

5. **Restart Browser**
   - Clears memory leaks
   - Fresh start

### Offline Mode Not Working

#### Symptoms
- Can't access app offline
- "No internet" error
- Missing features offline

#### Solutions

1. **Initial Online Visit Required**
   - Must visit once online
   - Service worker registration
   - WASM module caching

2. **Check Service Worker**
   - DevTools > Application > Service Workers
   - Verify "activated and running"

3. **Verify Mode**
   - Must be in Local Mode
   - Server Mode requires connection

4. **Cache Inspection**
   - DevTools > Application > Cache Storage
   - Verify resources cached

### Data Sync Issues (Server Mode)

#### Symptoms
- Data doesn't save
- Missing annotations
- Server errors

#### Solutions

1. **Check Server Status**
   - Verify backend running
   - Test API endpoint
   - Check server logs

2. **Network Issues**
   - Stable connection required
   - Check firewall/proxy
   - VPN interference

3. **Authentication**
   - Re-login if needed
   - Check session timeout

4. **Export as Backup**
   - Prevent data loss
   - Import later

### Installation Issues (PWA)

#### Symptoms
- No install button
- Installation fails
- App won't launch

#### Solutions

1. **Browser Support**
   - Verify PWA support
   - Update browser
   - Try Chrome/Edge

2. **HTTPS Required**
   - PWA requires HTTPS
   - localhost is exception

3. **Service Worker**
   - Must be registered
   - Check registration status

4. **Manifest Issues**
   - Check browser console
   - Verify manifest loads

### Database Issues (Local Mode)

#### Symptoms
- "Database error"
- Lost data
- Corrupted database

#### Solutions

1. **Export Backup First**
   - If possible, export immediately
   - Prevent total data loss

2. **Clear and Restore**
   - Clear site data
   - Import from backup

3. **IndexedDB Limits**
   - Check storage quota
   - Clear old data
   - Export archives

4. **Browser Update**
   - Update may fix bugs
   - Backup first

### Mode Switching Issues

#### Symptoms
- Can't switch modes
- App breaks after switch
- Data loss on switch

#### Solutions

1. **Export Before Switching**
   - Backup data first
   - Import after switch

2. **Complete Reload**
   - Allow full app reload
   - Don't interrupt process

3. **Clear Cache If Stuck**
   - Hard refresh
   - Clear service worker

## Error Messages

### "WebAssembly is not supported"

**Cause**: Browser too old or WASM disabled

**Solution**:
- Update browser to latest version
- Enable JavaScript
- Try modern browser (Chrome, Firefox, Edge)

### "Failed to initialize database"

**Cause**: IndexedDB blocked or corrupted

**Solution**:
- Check browser privacy settings
- Enable cookies and storage
- Clear site data and retry
- Try different browser

### "Service worker registration failed"

**Cause**: HTTPS requirement, browser settings, or extensions

**Solution**:
- Use HTTPS (or localhost)
- Disable interfering extensions
- Check browser console for details

### "Failed to load WASM module"

**Cause**: Network issue, CDN blocked, or memory

**Solution**:
- Check internet connection
- Allow CDN access (jsdelivr.net, unpkg.com)
- Free up memory
- Restart browser

### "Export failed"

**Cause**: Storage quota, permissions, or corrupted data

**Solution**:
- Check disk space
- Grant permissions
- Try different format
- Export smaller subset

## Platform-Specific Issues

### iOS Safari

**Known Issues:**
- Service worker cache limits
- Memory constraints
- Storage quota

**Solutions:**
- Regular data exports
- Clear cache periodically
- Use latest iOS version

### Firefox

**Known Issues:**
- Service worker update delays
- IndexedDB size limits

**Solutions:**
- Manual SW update (DevTools)
- Monitor storage usage
- Regular exports

### Edge

**Known Issues:**
- PWA installation quirks
- Chromium-based, similar to Chrome

**Solutions:**
- Same as Chrome solutions
- Update to latest Edge

## Getting More Help

### Before Seeking Help

1. **Check this guide first**
2. **Review FAQ**
3. **Check GitHub issues**
4. **Try solutions systematically**

### When Reporting Issues

Include:
- Browser name and version
- Operating system
- Mode (Server or Local)
- Exact error message
- Steps to reproduce
- Screenshots if relevant
- Browser console errors

### Where to Get Help

1. **GitHub Issues**
   - Search existing issues
   - Create new issue with details
   - Most effective for bugs

2. **User Guide**
   - Comprehensive usage info
   - Step-by-step instructions

3. **FAQ**
   - Common questions
   - Quick answers

### Debug Mode

Enable verbose logging:

1. Open browser console (F12)
2. Run: `localStorage.setItem('debug', 'true')`
3. Reload app
4. Review detailed logs

Disable: `localStorage.removeItem('debug')`

## Best Practices to Avoid Issues

1. **Regular Backups**
   - Weekly exports recommended
   - Store backups securely
   - Test restore occasionally

2. **Keep Browser Updated**
   - Latest version recommended
   - Security and compatibility

3. **Monitor Storage**
   - Don't hit quota limits
   - Regular cleanup
   - Archive old data

4. **Stable Network** (Server Mode)
   - Avoid unstable connections
   - Save frequently

5. **Quality Screenshots**
   - Clear, high-resolution
   - Proper lighting
   - Full graph visible

## Recovery Procedures

### Lost Data (Local Mode)

1. Check browser backup/sync
2. Look for exported files
3. Check system backup
4. If lost, start fresh

### Corrupted Database

1. Export what you can
2. Clear site data completely
3. Reload app fresh
4. Import backup
5. Verify data integrity

### App Won't Start

1. Incognito mode test
2. Different browser test
3. Clear all caches
4. Uninstall/reinstall PWA
5. Report persistent issues

---

**Still stuck?**

Open a detailed GitHub issue with all relevant information.

**Prevention is better than cure** - Regular backups save headaches!

**Last Updated:** 2025
