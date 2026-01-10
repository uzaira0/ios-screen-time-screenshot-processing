# Screenshot Annotation Backend API

A production-ready FastAPI backend for multi-user screenshot annotation with redundant annotations and consensus tracking.

## Features

- **Multi-user authentication** with JWT tokens
- **Queue management** - Users see different screenshots until redundancy factor is met
- **Consensus detection** - Automatic detection of disagreements between annotators
- **Integration** with existing screenshot processor
- **RESTful API** with automatic OpenAPI documentation
- **Database persistence** with SQLAlchemy and SQLite (easily upgradeable to PostgreSQL)

## Installation

### 1. Install Dependencies

```bash
# Install backend dependencies
pip install -e ".[web]"
```

### 2. Initialize Database

The database is automatically initialized when the FastAPI application starts. You can also initialize it manually:

```python
import asyncio
from src.screenshot_processor.web.database import init_db

asyncio.run(init_db())
```

## Running the Server

### Development Mode

```bash
uvicorn src.screenshot_processor.web.api.main:app --reload
```

The server will start on `http://localhost:8000`

### Production Mode

```bash
uvicorn src.screenshot_processor.web.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## API Documentation

Once the server is running, visit:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### Authentication

- `POST /api/auth/register` - Register a new user
- `POST /api/auth/login` - Login and get JWT token
- `GET /api/auth/me` - Get current user info

### Screenshots

- `GET /api/screenshots/next` - Get next screenshot for current user
- `GET /api/screenshots/disputed` - Get screenshots with disagreements
- `GET /api/screenshots/stats` - Get overall statistics
- `GET /api/screenshots/{id}` - Get specific screenshot
- `POST /api/screenshots/upload` - Upload new screenshot (admin only)
- `POST /api/screenshots/{id}/skip` - Skip a screenshot

### Annotations

- `POST /api/annotations` - Submit annotation
- `GET /api/annotations/history` - Get user's annotation history
- `GET /api/annotations/{id}` - Get specific annotation
- `PUT /api/annotations/{id}` - Update annotation
- `DELETE /api/annotations/{id}` - Delete annotation

### Consensus

- `GET /api/consensus/{screenshot_id}` - Get consensus analysis
- `GET /api/consensus/summary/stats` - Get consensus statistics
- `POST /api/consensus/{screenshot_id}/recalculate` - Force recalculate consensus

## Configuration

### Secret Key

**IMPORTANT**: Change the secret key in production!

Edit `src/screenshot_processor/web/services/auth_service.py`:

```python
SECRET_KEY = "your-production-secret-key-here"
```

Generate a secure secret key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Database URL

By default, the application uses SQLite. To use PostgreSQL:

Edit `src/screenshot_processor/web/database/database.py`:

```python
DATABASE_URL = "postgresql+asyncpg://user:password@localhost/dbname"
```

### CORS Origins

To allow requests from your React frontend, edit `src/screenshot_processor/web/api/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://yourfrontend.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Architecture

### Database Models

- **User** - User accounts with roles (admin/annotator)
- **Screenshot** - Screenshots to be annotated
- **Annotation** - User annotations with hourly values
- **ProcessingIssue** - Issues detected during processing
- **UserQueueState** - Tracks user queue state (pending/skipped/completed)
- **ConsensusResult** - Stores consensus analysis results

### Service Layer

- **AuthService** - Password hashing, JWT tokens, user authentication
- **ProcessorService** - Wraps existing ScreenshotProcessor
- **QueueService** - Queue management with redundancy factor
- **ConsensusService** - Disagreement detection and consensus calculation

### Queue Management

The queue system ensures:
1. Users don't see screenshots they've already annotated
2. Priority given to screenshots with fewer annotations
3. Disputed screenshots (with disagreements) are prioritized
4. Redundancy factor of 3 annotations per screenshot

### Consensus Detection

Consensus is calculated by:
1. Comparing hourly values across all annotations
2. Detecting disagreements (>5 minutes difference from median)
3. Calculating median values for consensus
4. Storing results in ConsensusResult table

## Testing

Run the import tests:

```bash
python test_backend_imports.py
```

## Example Usage

### 1. Register a User

```bash
curl -X POST "http://localhost:8000/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "annotator1",
    "email": "annotator1@example.com",
    "password": "securepassword123",
    "role": "annotator"
  }'
```

### 2. Login

```bash
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=annotator1&password=securepassword123"
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

### 3. Get Next Screenshot

```bash
curl -X GET "http://localhost:8000/api/screenshots/next" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### 4. Submit Annotation

```bash
curl -X POST "http://localhost:8000/api/annotations" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "screenshot_id": 1,
    "hourly_values": {
      "0": 10, "1": 5, "2": 0, ...
    },
    "extracted_title": "Instagram",
    "extracted_total": "2h 30m",
    "time_spent_seconds": 45.2
  }'
```

## Development

### Project Structure

```
src/screenshot_processor/web/
├── api/
│   ├── main.py              # FastAPI app
│   ├── dependencies.py      # Auth dependencies
│   └── routes/
│       ├── auth.py          # Auth endpoints
│       ├── screenshots.py   # Screenshot endpoints
│       ├── annotations.py   # Annotation endpoints
│       └── consensus.py     # Consensus endpoints
├── database/
│   ├── models.py            # SQLAlchemy models
│   ├── schemas.py           # Pydantic schemas
│   └── database.py          # DB connection
└── services/
    ├── auth_service.py      # Authentication
    ├── processor_service.py # Screenshot processing
    ├── queue_service.py     # Queue management
    └── consensus_service.py # Consensus detection
```

## Troubleshooting

### ModuleNotFoundError

If you get import errors, make sure you installed the web dependencies:

```bash
pip install -e ".[web]"
```

### Database Errors

Delete the database file and restart:

```bash
rm screenshot_annotations.db
uvicorn src.screenshot_processor.web.api.main:app --reload
```

## Next Steps

1. **Frontend Integration** - Build React frontend to consume this API
2. **Admin Panel** - Add admin dashboard for monitoring
3. **Export Features** - Add CSV export for consensus results
4. **Email Notifications** - Notify users of disagreements
5. **Rate Limiting** - Add rate limiting for API endpoints
6. **Logging** - Enhance logging for production monitoring
