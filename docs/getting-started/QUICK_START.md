# Quick Start Guide - Screenshot Annotation Platform

## Prerequisites

- **Python 3.10+** (you have 3.12.3 ✅)
- **Node.js 18+** and npm
- **Tesseract OCR** (for screenshot processing)

---

## Step 1: Install Backend Dependencies

```bash
# From the project root directory
pip3 install -e ".[web]"
```

This installs:
- FastAPI (web framework)
- SQLAlchemy (database ORM)
- Uvicorn (ASGI server)
- JWT authentication libraries
- All core processing dependencies

---

## Step 2: Initialize the Database

```bash
python3 -c "from src.screenshot_processor.web.database.database import init_db; init_db()"
```

This creates `screenshot_annotation.db` with all necessary tables.

---

## Step 3: Start the Backend Server

```bash
uvicorn src.screenshot_processor.web.api.main:app --reload --host 0.0.0.0 --port 8000
```

**Verify Backend:**
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

---

## Step 4: Install Frontend Dependencies

Open a **new terminal window**, then:

```bash
cd frontend
npm install
```

This installs React, TypeScript, TailwindCSS, Chart.js, and all dependencies.

---

## Step 5: Configure Frontend Environment

```bash
# In the frontend directory
cp .env.example .env
```

Edit `.env` file:
```env
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

---

## Step 6: Start the Frontend Dev Server

```bash
# Still in frontend directory
npm run dev
```

**Access Application:**
- Frontend: http://localhost:5173
- Opens automatically in browser

---

## Step 7: Create Your First User

1. Go to http://localhost:5173/register
2. Create an account:
   - Username: `admin`
   - Email: `admin@example.com`
   - Password: `admin123`
   - Check "Make me an admin"
3. Login with your credentials

---

## Step 8: Upload Screenshots

1. Click "Admin" in the navigation
2. Drag and drop screenshot files to the upload zone
3. Select image type (Battery or Screen Time)
4. Click "Upload"

---

## Step 9: Start Annotating

1. Go back to "Home" (Annotation page)
2. Click "Start Annotating"
3. The system will:
   - Load next screenshot
   - Auto-process (grid detection + OCR)
   - Show extracted data
4. If auto-detection fails:
   - Click upper-left corner of grid
   - Click lower-right corner of grid
   - Data will be extracted
5. Review the 24-hour chart
6. Edit any values if needed
7. Click "Submit" or press Enter

---

## Testing Multi-User Collaboration

### Open Two Browser Windows:

**Window 1:**
- Register as `user1@example.com`
- Start annotating

**Window 2:**
- Register as `user2@example.com`
- Start annotating (you'll get the same screenshot)

When user1 submits, user2 will see a live notification!

---

## Troubleshooting

### Backend won't start?

**Check if port 8000 is in use:**
```bash
# Linux/Mac
lsof -i :8000

# Windows (PowerShell)
Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess
```

**Use a different port:**
```bash
uvicorn src.screenshot_processor.web.api.main:app --reload --port 8001
```

Then update frontend `.env`:
```env
VITE_API_BASE_URL=http://localhost:8001
```

### Frontend won't start?

**Clear node_modules and reinstall:**
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

### Database errors?

**Reset database:**
```bash
rm screenshot_annotation.db
python3 -c "from src.screenshot_processor.web.database.database import init_db; init_db()"
```

### Import errors?

**Reinstall in development mode:**
```bash
pip3 uninstall screenshot-processor -y
pip3 install -e ".[web]"
```

---

## Quick Commands Reference

### Backend
```bash
# Install
pip3 install -e ".[web]"

# Initialize DB
python3 -c "from src.screenshot_processor.web.database.database import init_db; init_db()"

# Run server
uvicorn src.screenshot_processor.web.api.main:app --reload

# Run tests
pytest tests/integration/
```

### Frontend
```bash
# Install
cd frontend && npm install

# Development
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Type checking
npm run type-check
```

---

## What's Next?

- **Read the docs**: Check `README.md` for detailed feature documentation
- **Understand architecture**: See `ARCHITECTURE.md` for system design
- **Test thoroughly**: Follow `VERIFICATION_GUIDE.md` for testing procedures
- **Deploy to production**: See `DEPLOYMENT.md` for deployment guide

---

## Need Help?

- **Backend API docs**: http://localhost:8000/docs (interactive Swagger UI)
- **Architecture overview**: `ARCHITECTURE.md`
- **Testing guide**: `VERIFICATION_GUIDE.md`
- **Backend details**: `BACKEND_README.md`
