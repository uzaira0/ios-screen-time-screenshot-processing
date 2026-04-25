# Screenshot Processor - Frontend

A modern Progressive Web App (PWA) for processing iPhone battery and screen time screenshots with both server-based and client-side (WASM) processing modes.

## 🌟 Key Features

### Dual Processing Modes
- **Server Mode**: Fast GPU-accelerated processing, team collaboration, consensus features
- **Local Mode (WASM)**: 100% offline, complete privacy, no server required

### Progressive Web App (PWA)
- ✅ Installable on desktop and mobile
- ✅ Works completely offline
- ✅ Service Worker caching
- ✅ App-like experience
- ✅ Auto-updates

### Modern Architecture
- **React 18** with TypeScript for type safety
- **Vite** for blazing-fast development
- **Dependency Injection** for swappable backends
- **IndexedDB** for local data storage
- **Web Workers** for non-blocking processing

### Image Processing
- **OpenCV.js** for image manipulation
- **Tesseract.js** for OCR extraction
- **Auto-grid detection** with manual override
- **Dark mode conversion** automatic

### Data Management
- **Export**: CSV, Excel, JSON, full backups
- **Import**: Restore from backups
- **Validation**: Automatic data validation
- **Consensus**: Multi-annotator agreement tracking

---

## 📋 Prerequisites

- **Node.js** 18+ and npm 9+
- **Modern Browser**:
  - Chrome 90+
  - Firefox 88+
  - Safari 15+
  - Edge 90+

---

## 🚀 Quick Start

### WASM Mode (Standalone - No Backend Required)

```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173` - Works immediately with no configuration!

### Server Mode (With Backend)

1. **Start the backend first** (see backend README)

2. **Configure frontend:**
   ```bash
   cp .env.example .env
   # Edit .env and set: VITE_API_BASE_URL=http://localhost:8000/api
   ```

3. **Run frontend:**
   ```bash
   npm run dev
   ```

### Production Build

```bash
npm run build        # Builds for WASM mode by default
npm run preview      # Preview the build
```

**For Server Mode Build:**
```bash
VITE_API_BASE_URL=https://api.example.com/api npm run build
```

---

## 📁 Project Structure

```
frontend/
├── src/
│   ├── core/                          # Core architecture (Phase 1)
│   │   ├── interfaces/                # Service contracts
│   │   ├── implementations/
│   │   │   ├── server/               # Server-mode implementations
│   │   │   └── wasm/                 # WASM-mode implementations
│   │   │       ├── storage/          # IndexedDB (Phase 2)
│   │   │       └── processing/       # Image processing (Phase 3)
│   │   ├── di/                       # Dependency injection
│   │   ├── config/                   # Mode detection
│   │   ├── models/                   # Shared types
│   │   ├── hooks/                    # React hooks
│   │   └── monitoring/               # Performance tracking (Phase 4)
│   │
│   ├── components/
│   │   ├── layout/                   # Header, Layout
│   │   ├── auth/                     # Authentication
│   │   ├── annotation/               # Annotation workspace
│   │   ├── consensus/                # Consensus features
│   │   ├── queue/                    # Queue management
│   │   └── pwa/                      # PWA components (Phase 4)
│   │       ├── ModeSwitch.tsx        # Mode selector
│   │       ├── ExportDialog.tsx      # Export UI
│   │       ├── Onboarding.tsx        # First-time tutorial
│   │       ├── KeyboardShortcuts.tsx # Shortcut help
│   │       ├── OfflineBanner.tsx     # Offline detection
│   │       └── UpdateNotification.tsx # Update prompts
│   │
│   ├── pages/                        # Page components
│   ├── services/                     # Legacy API client
│   ├── store/                        # Zustand stores
│   ├── hooks/                        # Custom hooks
│   ├── types/                        # TypeScript types
│   ├── utils/                        # Utilities
│   ├── App.tsx                       # Main app with routing
│   ├── main.tsx                      # Entry point + PWA
│   └── index.css                     # Global styles
│
├── public/
│   ├── docs/                         # User documentation
│   │   ├── user-guide.md            # Complete user guide
│   │   ├── faq.md                   # FAQ
│   │   └── privacy-policy.md        # Privacy policy
│   ├── icons/                        # PWA icons
│   ├── offline.html                  # Offline fallback
│   └── manifest.webmanifest         # PWA manifest
│
├── package.json                      # Dependencies
├── tsconfig.json                     # TypeScript config
├── vite.config.ts                   # Vite + PWA config
├── tailwind.config.js               # Tailwind CSS
├── DEPLOYMENT.md                     # Deployment guide
└── README.md                         # This file
```

---

## 🔧 Configuration

### Environment Variables

**For WASM Mode (Default):**
No configuration needed! Just run `npm run dev`.

**For Server Mode:**
Create `.env` from `.env.example`:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Backend API URL (required for Server Mode)
VITE_API_BASE_URL=http://localhost:8000/api

# Optional Feature Flags
VITE_ENABLE_DEBUG=false
```

See `.env.example` for detailed configuration options.

### Processing Modes

The app automatically detects which modes are available:

**Mode Detection:**
- If `VITE_API_BASE_URL` is set → Both modes available, defaults to WASM
- If `VITE_API_BASE_URL` is empty → WASM mode only

**Switching Modes (UI):**
1. Go to **Settings** page
2. Select **Processing Mode** section
3. Choose between Server or Local (WASM) mode
4. Confirm mode switch
5. App reloads in new mode

**Switching Modes (Programmatically):**
```typescript
import { setAppMode } from '@/config/environment';

// Switch to WASM mode
setAppMode('wasm');

// Switch to Server mode (requires backend URL configured)
setAppMode('server');
```

**Current Mode:**
```typescript
import { useMode } from '@/hooks/useMode';

function MyComponent() {
  const { mode, config } = useMode();
  
  console.log(`Current mode: ${mode}`);
  console.log(`Can switch: ${config.canSwitchMode}`);
  console.log(`Server available: ${config.serverAvailable}`);
  
  return <div>Mode: {mode}</div>;
}
```

---

## 🎨 Key Features Explained

### 1. Progressive Web App (PWA)

**Install:**
- Desktop: Click install icon in address bar
- Mobile: Add to Home Screen

**Offline Support:**
- Service Worker caches all assets
- Works 100% offline after first load
- Automatic updates when online

**Configuration:**
- `vite.config.ts` - Vite PWA plugin
- `public/manifest.webmanifest` - App manifest
- `public/offline.html` - Offline fallback

### 2. Dual Processing Modes

**Server Mode:**
- Fast GPU processing
- Team collaboration
- Centralized storage
- Real-time consensus

**Local Mode:**
- Complete privacy
- Offline capable
- Browser-based processing
- Local IndexedDB storage

**Switching:**
- Settings → Processing Mode
- Data preserved
- Reload required

### 3. Image Processing (WASM)

**Libraries:**
- OpenCV.js (image manipulation)
- Tesseract.js (OCR)
- Comlink (Web Workers)

**Features:**
- Auto-grid detection
- Dark mode conversion
- Bar height analysis
- OCR text extraction

**Performance:**
- Runs in Web Worker
- Non-blocking UI
- 2-10 seconds processing

### 4. Export/Import

**Export Formats:**
- CSV: Simple spreadsheet
- Excel: Multiple sheets
- JSON: Complete data
- Backup: Full database

**Import:**
- Restore from backups
- Merge or replace data
- Progress tracking

### 5. Onboarding & Help

**First-Time Tutorial:**
- 6-step onboarding
- Feature highlights
- Keyboard shortcuts
- Best practices

**Keyboard Shortcuts:**
- `Ctrl/Cmd + K`: Show shortcuts
- `Ctrl/Cmd + S`: Save annotation
- `Ctrl/Cmd + E`: Export data
- `Ctrl/Cmd + U`: Upload screenshot

### 6. Offline Detection

**Features:**
- Automatic online/offline detection
- Banner notification
- Graceful degradation
- Auto-sync when reconnected

---

## 🛠️ Development

### Available Scripts

```bash
# Development
npm run dev              # Start dev server
npm run type-check      # TypeScript type checking

# Production
npm run build           # Production build
npm run preview         # Preview production build

# Testing (future)
npm test                # Run tests
npm run test:coverage   # Coverage report
```

### Development Server

**Features:**
- Hot Module Replacement (HMR)
- API proxy to backend
- TypeScript checking
- Fast refresh

**Proxy Configuration:**
```typescript
// vite.config.ts
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true
    }
  }
}
```

### Build Optimization

**Vite Configuration:**
- Code splitting by route
- Manual chunks for vendors
- Tree shaking enabled
- Minification
- Gzip compression

**Bundle Analysis:**
```bash
npm run build
npx vite-bundle-visualizer
```

---

## 📱 PWA Features

### Service Worker

**Caching Strategy:**
- **App Shell**: Precache (install time)
- **Images**: Cache-first
- **WASM**: Cache-first
- **API**: Network-first
- **CDN**: Cache-first (1 year)

**Update Strategy:**
- Prompt on new version
- Background update
- User confirmation
- Automatic activation

### Manifest

**PWA Manifest Fields:**
```json
{
  "name": "Screenshot Processor",
  "short_name": "ScreenProc",
  "display": "standalone",
  "theme_color": "#3b82f6",
  "background_color": "#ffffff",
  "icons": [...],
  "categories": ["productivity", "utilities"]
}
```

### Icons Required

**Sizes:**
- 192x192 (any + maskable)
- 512x512 (any + maskable)

**Screenshots:**
- Desktop: 1280x720 (wide)
- Mobile: 750x1334 (narrow)

**Generate Icons:**
```bash
# Use PWA Asset Generator
npx pwa-asset-generator logo.svg ./public/icons
```

---

## 🚢 Deployment

See [DEPLOYMENT.md](./DEPLOYMENT.md) for detailed deployment guides:

- GitHub Pages
- Docker
- Self-hosting

### Quick Deploy

**Docker:**
```bash
docker build -t screenshot-processor .
docker run -p 80:80 screenshot-processor
```

---

## 📊 Performance

### Lighthouse Targets

- **Performance**: > 90
- **Accessibility**: > 95
- **Best Practices**: > 95
- **SEO**: > 90
- **PWA**: 100

### Run Lighthouse

```bash
npm run build
npm run preview

# In another terminal
npx lighthouse http://localhost:4173 --view
```

### Performance Monitoring

**Built-in:**
- Processing time tracking
- Memory usage monitoring
- Core Web Vitals
- Error tracking

**Usage:**
```typescript
import { PerformanceMonitor } from '@/core/monitoring';

// Track processing
const timer = PerformanceMonitor.measureProcessingTime(screenshotId);
// ... do processing ...
timer.end(success);

// Get summary
const summary = PerformanceMonitor.getSummary();
console.log(summary);
```

---

## 🔐 Security

### Content Security Policy

**Recommended CSP:**
```html
<meta http-equiv="Content-Security-Policy" 
      content="default-src 'self'; 
               script-src 'self' 'wasm-unsafe-eval'; 
               style-src 'self' 'unsafe-inline'; 
               img-src 'self' data: blob:;">
```

### Data Privacy

**Local Mode:**
- Zero data transmission
- All processing in browser
- No tracking/analytics
- Complete privacy

**Server Mode:**
- Data transmitted to server
- Subject to server policies
- Authentication required
- HTTPS recommended

See [privacy-policy.md](./public/docs/privacy-policy.md) for details.

---

## 🧪 Testing

### Manual Testing Checklist

**PWA:**
- [ ] App installs on desktop
- [ ] App installs on mobile
- [ ] Works offline
- [ ] Service Worker registers
- [ ] Update notification shows

**Processing:**
- [ ] Server mode works
- [ ] WASM mode works
- [ ] Mode switching works
- [ ] Grid detection works
- [ ] OCR extraction accurate

**Export/Import:**
- [ ] CSV export works
- [ ] Excel export works
- [ ] JSON export works
- [ ] Backup/restore works

**UI/UX:**
- [ ] Onboarding shows
- [ ] Keyboard shortcuts work
- [ ] Offline banner shows
- [ ] Responsive on mobile
- [ ] Accessible (screen reader)

---

## 📚 Documentation

### User Documentation

- **[User Guide](./public/docs/user-guide.md)**: Complete usage guide
- **[FAQ](./public/docs/faq.md)**: Frequently asked questions
- **[Privacy Policy](./public/docs/privacy-policy.md)**: Privacy information

### Developer Documentation

- **[DEPLOYMENT.md](./DEPLOYMENT.md)**: Deployment guide
- **Architecture**: Phase 1-3 summary documents
- **API Docs**: Backend API documentation

### In-App Help

- Press `Ctrl/Cmd + K` for keyboard shortcuts
- Click `?` icon for user guide
- Settings → About for version info

---

## 🤝 Contributing

### Code Style

- TypeScript for all new code
- Prettier for formatting
- ESLint for linting
- Conventional commits

### Pull Requests

1. Fork the repository
2. Create feature branch
3. Make changes
4. Run type check
5. Test thoroughly
6. Submit PR

### Reporting Issues

Include:
- Browser version
- Processing mode
- Steps to reproduce
- Screenshots
- Console errors

---

## 🔄 Version History

### Phase 4 (Current) - PWA & Production Polish
- ✅ Progressive Web App
- ✅ Offline support
- ✅ Export enhancements
- ✅ Performance monitoring
- ✅ User documentation
- ✅ Deployment guides

### Phase 3 - Image Processing (WASM)
- ✅ OpenCV.js integration
- ✅ Tesseract.js OCR
- ✅ Web Worker processing
- ✅ Grid detection
- ✅ Bar extraction

### Phase 2 - IndexedDB Storage
- ✅ Local data persistence
- ✅ Blob storage
- ✅ Export/import
- ✅ Data migration

### Phase 1 - DI Architecture
- ✅ Service abstraction
- ✅ Dependency injection
- ✅ Mode switching
- ✅ Zero code duplication

---

## 📄 License

MIT

---

## 🆘 Support

- **GitHub Issues**: Bug reports and feature requests
- **Documentation**: Check user guide and FAQ
- **Community**: Discussions on GitHub

---

**Built with ❤️ using React, TypeScript, and Vite**
