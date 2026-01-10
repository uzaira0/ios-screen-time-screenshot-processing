# iOS Screen Time Screenshot Processing

A comprehensive full-stack web application for processing and collaboratively annotating iOS battery and screen time usage screenshots with real-time updates, consensus detection, and administrative controls.

## Overview

This platform enables multiple annotators to independently extract hourly usage data from screenshots, automatically detects disagreements between annotations, and provides administrative oversight through an advanced dashboard.

### Key Features

- **Automated OCR Processing**: Automatic grid detection and hourly value extraction using Tesseract OCR
- **Manual Annotation Fallback**: Interactive grid selection when auto-processing fails
- **Multi-User Redundancy**: Configurable number of independent annotations per screenshot (default: 3)
- **Real-Time Collaboration**: WebSocket-based live updates when users join, submit annotations, or reach consensus
- **Consensus Detection**: Automated disagreement analysis with severity classification (minor/moderate/major)
- **Admin Dashboard**: Comprehensive analytics, user management, bulk upload, and data export
- **Disagreement Heatmap**: Visual representation of annotation disagreements across screenshots
- **Header-Based Authentication**: Simple username-based authentication for internal research tools

---

## Project Structure

```
ios-screen-time-screenshot-processing/
├── src/screenshot_processor/          # Python package (pip installable)
│   ├── core/                          # Core processing logic (OCR, image processing)
│   ├── gui/                           # PyQt6 desktop GUI
│   └── web/                           # FastAPI web backend
│       ├── api/                       # REST API routes
│       ├── database/                  # SQLAlchemy models and Pydantic schemas
│       ├── services/                  # Business logic layer
│       ├── repositories/              # Database query layer
│       └── websocket/                 # WebSocket connection manager
│
├── frontend/                          # React + TypeScript webapp
│   ├── src/
│   │   ├── core/                      # DI architecture (mode-agnostic)
│   │   │   └── implementations/
│   │   │       ├── server/            # API mode (multi-user)
│   │   │       └── wasm/              # WASM mode (client-side only)
│   │   ├── components/                # React components
│   │   ├── pages/                     # Page components
│   │   ├── hooks/                     # Custom React hooks
│   │   ├── store/                     # Zustand state management (slices/)
│   │   └── types/                     # TypeScript types (api-schema.ts auto-generated)
│   └── tests/                         # Playwright E2E tests
│
├── docs/                              # Documentation
│   ├── architecture/                  # System architecture docs
│   ├── deployment/                    # Deployment guides
│   ├── getting-started/               # Quick start guides
│   └── guides/                        # How-to guides
│
├── docker/                            # Docker configurations
│   ├── backend/                       # Backend Dockerfile
│   ├── frontend/                      # Frontend Dockerfiles (prod, dev, wasm)
│   ├── nginx/                         # Nginx configs
│   └── docker-compose.*.yml           # Compose files (dev, prod, wasm)
│
├── scripts/                           # Utility scripts
├── tests/                             # Backend test suite
│   ├── integration/                   # Integration tests
│   ├── unit/                          # Unit tests
│   └── fixtures/                      # Test data and images
│
├── alembic/                           # Database migrations
├── data/                              # [gitignored] Data files
├── uploads/                           # [gitignored] Screenshot storage
└── db/                                # [gitignored] Database files
```

---

## Quick Start

### Prerequisites

- **Python 3.10+**
- **Node.js 18+**
- **PostgreSQL 14+**
- **Tesseract OCR** (install via system package manager)

### Backend Setup

1. **Install Python dependencies** (using uv):
   ```bash
   uv sync                               # Install all dependencies
   # Or with pip:
   pip install -e ".[web,dev]"
   ```

2. **Start PostgreSQL** (Docker recommended):
   ```bash
   docker compose -f docker/docker-compose.dev.yml up -d
   ```

3. **Configure environment variables** (copy `.env.example` to `.env`):
   ```bash
   DATABASE_URL=postgresql+asyncpg://screenshot:screenshot@localhost:5435/screenshot_annotations
   SECRET_KEY=your-super-secret-key-change-in-production
   UPLOAD_API_KEY=your-api-key-for-programmatic-uploads
   ```

4. **Run database migrations**:
   ```bash
   alembic upgrade head
   ```

5. **Start backend server**:
   ```bash
   uvicorn src.screenshot_processor.web.api.main:app --reload --host 127.0.0.1 --port 8002
   ```

### Frontend Setup

1. **Install Node.js dependencies**:
   ```bash
   cd frontend
   npm install
   ```

2. **Configure environment variables** (create `frontend/.env`):
   ```bash
   VITE_API_BASE_URL=http://localhost:8002/api/v1
   VITE_WS_URL=ws://localhost:8002/api/v1/ws
   ```

3. **Generate TypeScript types from Pydantic schemas**:
   ```bash
   npm run generate:api-types        # Generates src/types/api-schema.ts from OpenAPI spec
   ```

4. **Start development server**:
   ```bash
   npm run dev
   ```

5. **Access the application**:
   - Frontend: http://localhost:5175
   - Backend API: http://localhost:8002
   - API Docs: http://localhost:8002/docs

---

## User Workflows

### Annotator Workflow

1. **Register/Login**: Create account or login at `/login`
2. **Get Assignment**: Navigate to `/annotate` to receive next available screenshot
3. **Review Auto-Processing**: Check automatically detected grid and extracted values
4. **Manual Correction** (if needed): Click corners to redefine grid boundaries
5. **Verify Data**: Review 24-hour values, title, and total
6. **Submit**: Submit annotation and receive next screenshot
7. **View History**: Check past annotations at `/history`

### Admin Workflow

1. **Access Dashboard**: Navigate to `/admin` (admin role required)
2. **Upload Screenshots**: Bulk drag-and-drop upload with automatic processing
3. **Monitor Stats**: View real-time completion rates, user activity, and disputed screenshots
4. **Review Disagreements**: Use heatmap to identify problematic screenshots
5. **Manage Users**: Activate/deactivate users, promote to admin
6. **Export Data**: Download consensus results as CSV with all hourly values

---

## Real-Time Features

### WebSocket Events

The platform broadcasts the following events to all connected users:

- `annotation_submitted`: User completed an annotation
- `screenshot_completed`: Screenshot reached required annotation count
- `consensus_disputed`: Disagreement detected between annotations
- `user_joined`: New user connected
- `user_left`: User disconnected

### Live Updates

- **Toast Notifications**: Real-time alerts for all WebSocket events
- **Active Users Counter**: Shows number of currently connected users (admin dashboard)
- **Progress Updates**: Stats refresh automatically when screenshots are completed
- **Consensus Status**: Live updates when consensus is reached or disputed

---

## Consensus Detection

### Disagreement Thresholds

- **Minor**: Difference ≤ 2 minutes
- **Moderate**: Difference ≤ 5 minutes
- **Major**: Difference > 5 minutes

### Consensus Strategies

The system supports multiple strategies for calculating consensus values:

- **Median** (default): Middle value among all annotations
- **Mean**: Average of all annotation values
- **Mode**: Most frequently occurring value (falls back to median if no mode exists)

### Disagreement Resolution

1. **Automatic Detection**: System analyzes all annotations when 2+ exist
2. **Severity Classification**: Each disagreement hour is categorized by severity
3. **Admin Review**: Disputed screenshots appear in `/disputed` and admin heatmap
4. **Manual Adjudication**: Admins can review all user annotations side-by-side

---

## Security Notice

> **Important**: This application uses **header-based authentication** (`X-Username` header) which is designed for **internal research tools on trusted networks only**.
>
> **Limitations:**
> - No password verification - any user can claim any username
> - No JWT tokens - session state is header-based only
> - Users are auto-created on first request
> - Admin access is granted to users with username "admin"
>
> **For production deployment:**
> - Deploy only on trusted internal networks
> - Use network-level security (VPN, firewall rules)
> - Do NOT expose to the public internet without implementing proper authentication
>
> If you need to expose this application externally, implement proper JWT or OAuth2 authentication first.

---

## API Documentation

All endpoints are prefixed with `/api/v1/`. See http://localhost:8002/docs for interactive API documentation.

### Authentication Endpoints

- `POST /api/v1/auth/login` - Login (X-Username header, auto-creates users)
- `GET /api/v1/auth/me` - Get current user profile

### Screenshot Endpoints

- `GET /api/v1/screenshots/next` - Get next unassigned screenshot
- `GET /api/v1/screenshots/{id}` - Get screenshot by ID
- `GET /api/v1/screenshots/{id}/image` - Get screenshot image file
- `GET /api/v1/screenshots/stats` - Get queue statistics
- `POST /api/v1/screenshots/upload` - Upload screenshot (X-API-Key auth)

### Annotation Endpoints

- `POST /api/v1/annotations/` - Submit new annotation
- `GET /api/v1/annotations/history` - Get user's annotation history

### Consensus Endpoints

- `GET /api/v1/consensus/{screenshot_id}` - Get consensus analysis for screenshot

### Admin Endpoints (Requires Admin Role)

- `GET /api/v1/admin/users` - List all users with activity data
- `PUT /api/v1/admin/users/{id}` - Update user status or role
- `DELETE /api/v1/admin/groups/{id}` - Delete group and all screenshots
- `POST /api/v1/admin/reset-test-data` - Reset test data for e2e tests

### WebSocket Endpoint

- `WS /api/v1/ws` - Real-time event streaming (X-Username header auth)

### Type Generation

TypeScript types are auto-generated from Pydantic schemas via OpenAPI:

```bash
cd frontend
npm run generate:api-types    # Generates src/types/api-schema.ts
```

This ensures **Pydantic is the single source of truth** for API contracts.

---

## Testing

### Backend Integration Tests

Run comprehensive workflow tests:

```bash
pytest tests/integration/ -v
```

Tests cover:
- Complete annotation workflow
- Multi-user redundancy (3 annotations per screenshot)
- Disagreement detection
- Consensus calculation
- WebSocket event broadcasting

### Frontend E2E Test Plan

See [frontend/E2E_TEST_PLAN.md](frontend/E2E_TEST_PLAN.md) for comprehensive manual testing scenarios covering:
- Auto-processing success/failure
- Manual grid selection
- Multi-user consensus
- Real-time notifications
- Admin dashboard functionality

---

## Deployment

See [docs/deployment/DEPLOYMENT.md](docs/deployment/DEPLOYMENT.md) for comprehensive production deployment guide including:

- Environment configuration
- Database setup (PostgreSQL with async support)
- Nginx reverse proxy configuration with WebSocket support
- SSL certificate setup
- Systemd service configuration
- Performance tuning recommendations

---

## Architecture

See [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) for detailed system architecture including:

- Full-stack component diagram
- Database schema (ERD)
- WebSocket event flow
- Consensus algorithm details
- Security model
- Technology stack rationale

---

## Desktop GUI

The PyQt6 desktop application is available for standalone use:

```bash
python -m screenshot_processor.gui.main_window
```

**Features**:
- Batch processing of screenshot folders
- Manual grid selection with magnifying glass
- CSV export of extracted data
- Offline operation

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

---

## License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## Disclaimers

Not affiliated with Apple Inc. "iOS" and "Screen Time" are trademarks of Apple Inc.

The original screenshot processing approach is based on Arcascope's [screen-scrape](https://github.com/Arcascope/screen-scrape) tool. This project is an independent reimplementation and is not affiliated with or endorsed by Arcascope.

## AI Disclaimer

This application was developed with the assistance of artificial intelligence tools including Claude (Anthropic), ChatGPT (OpenAI), GitHub Copilot, and Gemini (Google).

---

## Acknowledgments

- **[Arcascope screen-scrape](https://github.com/Arcascope/screen-scrape)**: Original screenshot scraping tool that inspired this project
- **Tesseract OCR**: Optical character recognition engine
- **FastAPI**: Modern Python web framework
- **React + Vite**: Frontend framework and build tool
- **SQLAlchemy**: Python SQL toolkit and ORM
- **PyQt6**: Python bindings for Qt framework (desktop GUI)
