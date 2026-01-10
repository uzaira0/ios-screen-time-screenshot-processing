# Ephemeral RAM-Only Processing Guide

## Changes Needed for RAM-Only Mode

### 1. Modify Upload Endpoint
Don't save files to disk, keep in memory:

```python
# Current: Saves to disk
@router.post("/upload")
async def upload_screenshot(file: UploadFile):
    file_path = f"./uploads/{file.filename}"
    with open(file_path, "wb") as f:
        f.write(await file.read())  # ❌ Disk write

# RAM-only version
@router.post("/upload")
async def upload_screenshot(file: UploadFile):
    contents = await file.read()  # Keep in memory
    result = await process_from_bytes(contents, file.content_type)
    return result  # No disk storage
```

### 2. Update Image Processor
Accept bytes instead of file paths:

```python
# Add new function
def process_from_bytes(image_bytes: bytes, image_type: str) -> dict:
    # Decode image from bytes
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    # Process normally
    result = process_image(img, image_type)
    
    return result
    # img deleted automatically when function ends
```

### 3. Remove Debug Image Saves
Delete all disk writes:

```python
# Remove these
cv2.imwrite("debug/processed.jpg", img)  # ❌
Path("output").mkdir()  # ❌
```

### 4. Use RAM Disk (Optional)
For any temp files:

```bash
# Mount tmpfs (RAM disk)
sudo mount -t tmpfs -o size=1G tmpfs /tmp/processing

# Configure Python to use it
TMPDIR=/tmp/processing python app.py
```

### 5. Add Privacy Statement
In your API docs:

```python
@app.get("/")
async def root():
    return {
        "privacy": "All image processing happens in RAM. "
                   "No images are saved to disk. "
                   "Data is deleted when request completes."
    }
```

## Verification Steps

Users can verify by:

1. **Check disk usage** - Shouldn't increase
```bash
watch -n 1 df -h /
```

2. **Monitor file operations**
```bash
sudo lsof -p $(pidof python) | grep .jpg
# Should show zero image files open
```

3. **Memory usage** - Should spike temporarily
```bash
watch -n 1 free -h
```

## Trade-offs

**Pros:**
- True privacy - images never persisted
- Faster (no disk I/O)
- Auto-cleanup (GC handles it)

**Cons:**
- Can't review/debug later
- RAM limits batch size
- Can't re-process without re-upload

## Current Implementation vs Ephemeral

| Feature | Current (Disk) | Ephemeral (RAM) |
|---------|---------------|-----------------|
| Upload saves file | ✓ Yes | ✗ No |
| Debug images | ✓ Yes | ✗ No |
| Database stores path | ✓ Yes | ✗ Only results |
| Can reprocess | ✓ Yes | ✗ Must re-upload |
| Privacy | Medium | High |
| Speed | Slower | Faster |
