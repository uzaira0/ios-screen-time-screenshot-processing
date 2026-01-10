# System Architecture

## Table of Contents

1. [Overview](#overview)
2. [Technology Stack](#technology-stack)
3. [System Components](#system-components)
4. [Database Schema](#database-schema)
5. [API Architecture](#api-architecture)
6. [WebSocket Architecture](#websocket-architecture)
7. [Consensus Algorithm](#consensus-algorithm)
8. [Security Model](#security-model)
9. [Data Flow](#data-flow)
10. [Performance Considerations](#performance-considerations)

---

## Overview

The Screenshot Annotation Platform is a full-stack web application designed for collaborative annotation of iPhone battery and screen time usage screenshots. The system employs a modern microservices-inspired architecture with clear separation of concerns.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Layer                             │
│  ┌────────────────┐        ┌──────────────────────────┐         │
│  │  React SPA     │◄─────►│  WebSocket Client        │         │
│  │  (Vite)        │        │  (Auto-reconnect)        │         │
│  └────────────────┘        └──────────────────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              │           │
                         HTTP │           │ WS
                              ▼           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Application Layer                           │
│  ┌────────────────┐        ┌──────────────────────────┐         │
│  │  FastAPI       │        │  WebSocket Manager       │         │
│  │  REST API      │        │  (Connection Pool)       │         │
│  └────────────────┘        └──────────────────────────┘         │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────────────────────────────────┐                │
│  │          Service Layer                      │                │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────┐    │                │
│  │  │  Auth   │ │ Consensus│ │ Processor│    │                │
│  │  │ Service │ │ Service  │ │ Service  │    │                │
│  │  └─────────┘ └──────────┘ └──────────┘    │                │
│  └─────────────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Data Layer                                │
│  ┌────────────────┐        ┌──────────────────────────┐         │
│  │  PostgreSQL    │        │  File Storage            │         │
│  │  (Async)       │        │  (Screenshots)           │         │
│  └────────────────┘        └──────────────────────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

### Backend

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Framework | FastAPI | 0.104+ | Async web framework with OpenAPI |
| ORM | SQLAlchemy | 2.0+ | Async database ORM |
| Database | PostgreSQL | 14+ | Primary data store |
| Database Driver | asyncpg | Latest | Async PostgreSQL driver |
| Authentication | python-jose | Latest | JWT token handling |
| Password Hashing | passlib | Latest | Bcrypt password hashing |
| OCR | pytesseract | Latest | Tesseract wrapper |
| Image Processing | OpenCV, PIL | Latest | Image manipulation |
| WebSocket | FastAPI WebSocket | Built-in | Real-time bidirectional communication |

### Frontend

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Framework | React | 18+ | UI component library |
| Language | TypeScript | 5+ | Type-safe JavaScript |
| Build Tool | Vite | 5+ | Fast build and HMR |
| HTTP Client | Axios | Latest | API requests with interceptors |
| State Management | Zustand | Latest | Lightweight state management |
| Routing | React Router | 6+ | Client-side routing |
| Notifications | react-hot-toast | Latest | Toast notifications |
| File Upload | react-dropzone | Latest | Drag-and-drop file upload |
| Styling | Tailwind CSS | 3+ | Utility-first CSS |

---

## System Components

### 1. Authentication Service (`auth_service.py`)

**Responsibilities**:
- User registration and login
- Password hashing with bcrypt
- JWT token generation and validation
- Role-based access control (admin/annotator)

**Key Functions**:
- `create_user(db, username, email, password)` - Register new user
- `authenticate_user(db, username, password)` - Verify credentials
- `create_access_token(data, expires_delta)` - Generate JWT
- `get_current_user(token, db)` - Dependency for protected routes

### 2. Processor Service (`processor_service.py`)

**Responsibilities**:
- Screenshot auto-processing
- OCR grid detection
- Hourly value extraction
- Error handling and issue tracking

**Key Functions**:
- `process_screenshot(screenshot)` - Main processing pipeline
- `detect_grid(image)` - Automatic grid boundary detection
- `extract_hourly_values(grid_image)` - OCR value extraction
- `save_processing_issues(annotation, issues)` - Error logging

### 3. Consensus Service (`consensus_service.py`)

**Responsibilities**:
- Multi-user annotation comparison
- Disagreement detection and classification
- Consensus value calculation
- Severity analysis

**Key Functions**:
- `analyze_consensus(db, screenshot_id, strategy)` - Main consensus analysis
- `calculate_consensus_value(values, strategy)` - Value aggregation (median/mean/mode)
- `classify_disagreement_severity(max_diff)` - Minor/moderate/major classification

**Algorithms**:

```python
# Consensus Value Calculation
def calculate_consensus_value(values, strategy):
    if strategy == MEDIAN:
        return statistics.median(values)
    elif strategy == MEAN:
        return statistics.mean(values)
    elif strategy == MODE:
        try:
            return statistics.mode(values)
        except StatisticsError:
            return statistics.median(values)  # Fallback

# Disagreement Severity Classification
def classify_disagreement_severity(max_diff):
    if max_diff == 0:
        return NONE
    elif max_diff <= 2:  # 2 minutes
        return MINOR
    elif max_diff <= 5:  # 5 minutes
        return MODERATE
    else:
        return MAJOR
```

### 4. Queue Service (`queue_service.py`)

**Responsibilities**:
- Screenshot assignment to users
- Load balancing across annotators
- Preventing duplicate assignments
- Queue statistics calculation

**Key Functions**:
- `get_next_screenshot(db, user_id)` - Assign next pending screenshot
- `get_queue_stats(db)` - Calculate completion progress

**Assignment Logic**:

```python
# Prioritize screenshots with fewest annotations
# Exclude screenshots already annotated by current user
SELECT screenshots.*
FROM screenshots
LEFT JOIN annotations ON screenshots.id = annotations.screenshot_id
  AND annotations.user_id = :current_user_id
WHERE screenshots.status = 'pending'
  AND screenshots.current_annotation_count < screenshots.required_annotations
  AND annotations.id IS NULL  -- User hasn't annotated this yet
ORDER BY screenshots.current_annotation_count ASC, screenshots.uploaded_at ASC
LIMIT 1
```

### 5. WebSocket Manager (`manager.py`)

**Responsibilities**:
- Active connection management
- Event broadcasting
- User presence tracking
- Connection health monitoring

**Key Features**:
- Per-user connection storage (`dict[user_id, WebSocket]`)
- User metadata tracking (username, connection time)
- Graceful disconnection handling
- Error recovery and cleanup

**Event Broadcasting**:

```python
class ConnectionManager:
    async def broadcast(self, event: WebSocketEvent):
        """Send event to all connected users"""
        disconnected_users = []
        for user_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json(event.model_dump())
            except Exception:
                disconnected_users.append(user_id)

        # Cleanup disconnected users
        for user_id in disconnected_users:
            self.disconnect(user_id)

    async def broadcast_except(self, event: WebSocketEvent, exclude_user_id: int):
        """Send event to all users except specified one"""
        # Similar logic, skip exclude_user_id
```

---

## Database Schema

### Entity-Relationship Diagram

```
┌─────────────────┐
│     users       │
├─────────────────┤
│ id (PK)         │
│ username        │◄───────┐
│ email           │        │
│ hashed_password │        │
│ role            │        │
│ is_active       │        │
│ created_at      │        │
└─────────────────┘        │
                           │
                           │ uploaded_by_id
                           │
┌─────────────────┐        │
│  screenshots    │        │
├─────────────────┤        │
│ id (PK)         │        │
│ file_path       │        │
│ image_type      │        │
│ status          │        │
│ required_annots │        │
│ current_annots  │        │
│ has_consensus   │        │
│ uploaded_by_id  ├────────┘
│ uploaded_at     │
└────┬────────────┘
     │
     │ screenshot_id
     │
     ├──────────────────────┐
     │                      │
┌────▼────────────┐  ┌──────▼──────────────┐
│  annotations    │  │  consensus_results  │
├─────────────────┤  ├─────────────────────┤
│ id (PK)         │  │ id (PK)             │
│ screenshot_id   │  │ screenshot_id       │
│ user_id (FK)    │  │ has_consensus       │
│ hourly_values   │  │ consensus_values    │
│ extracted_title │  │ disagreement_details│
│ extracted_total │  │ created_at          │
│ grid_upper_left │  │ updated_at          │
│ grid_lower_right│  └─────────────────────┘
│ time_spent_sec  │
│ notes           │
│ status          │
│ created_at      │
└────┬────────────┘
     │
     │ annotation_id
     │
┌────▼─────────────┐
│ processing_issues│
├──────────────────┤
│ id (PK)          │
│ annotation_id    │
│ issue_type       │
│ severity         │
│ message          │
│ created_at       │
└──────────────────┘
```

### Table Specifications

#### users

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Auto-incrementing user ID |
| username | VARCHAR(50) | UNIQUE, NOT NULL | Unique username |
| email | VARCHAR(255) | UNIQUE, NOT NULL | Email address |
| hashed_password | VARCHAR(255) | NOT NULL | Bcrypt hashed password |
| role | VARCHAR(20) | NOT NULL, DEFAULT 'annotator' | User role (admin/annotator) |
| is_active | BOOLEAN | NOT NULL, DEFAULT TRUE | Account status |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Account creation time |

#### screenshots

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Auto-incrementing screenshot ID |
| file_path | VARCHAR(500) | UNIQUE, NOT NULL | Path to image file |
| image_type | VARCHAR(20) | NOT NULL | Battery or ScreenTime |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'pending' | pending/completed |
| required_annotations | INTEGER | NOT NULL, DEFAULT 3 | Required annotation count |
| current_annotation_count | INTEGER | NOT NULL, DEFAULT 0 | Actual annotation count |
| has_consensus | BOOLEAN | DEFAULT NULL | Consensus reached flag |
| uploaded_by_id | INTEGER | FOREIGN KEY → users.id | Uploader user ID |
| uploaded_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Upload timestamp |

#### annotations

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Auto-incrementing annotation ID |
| screenshot_id | INTEGER | FOREIGN KEY → screenshots.id | Associated screenshot |
| user_id | INTEGER | FOREIGN KEY → users.id | Annotator user ID |
| hourly_values | JSONB | NOT NULL | {"0": 10.5, "1": 15.2, ...} |
| extracted_title | VARCHAR(255) | | Title from screenshot |
| extracted_total | FLOAT | | Total usage (minutes) |
| grid_upper_left | INTEGER[] | | [x, y] coordinates |
| grid_lower_right | INTEGER[] | | [x, y] coordinates |
| time_spent_seconds | INTEGER | | Annotation duration |
| notes | TEXT | | User notes |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'submitted' | Annotation status |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Submission time |

**Unique Constraint**: (screenshot_id, user_id) - Prevents duplicate annotations by same user

#### consensus_results

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Auto-incrementing result ID |
| screenshot_id | INTEGER | FOREIGN KEY → screenshots.id, UNIQUE | Associated screenshot |
| has_consensus | BOOLEAN | NOT NULL | Consensus achieved flag |
| consensus_values | JSONB | | {"0": 12.0, "1": 18.5, ...} |
| disagreement_details | JSONB | | Structured disagreement data |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Creation time |
| updated_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Last update time |

**Disagreement Details Structure**:

```json
{
  "total_disagreements": 3,
  "disagreement_hours": ["0", "12", "18"],
  "details": [
    {
      "hour": "0",
      "values": [10.0, 15.0, 12.0],
      "consensus_value": 12.0,
      "has_disagreement": true,
      "max_difference": 5.0,
      "severity": "moderate",
      "strategy_used": "median"
    }
  ]
}
```

---

## API Architecture

### Request/Response Flow

```
Client Request
      │
      ▼
┌─────────────────────┐
│  CORS Middleware    │  (Allow cross-origin requests)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Authentication     │  (JWT validation via dependency)
│  Middleware         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Route Handler      │  (FastAPI endpoint function)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Service Layer      │  (Business logic)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Database Session   │  (SQLAlchemy async session)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Response Formatting│  (Pydantic serialization)
└──────────┬──────────┘
           │
           ▼
      JSON Response
```

### Dependency Injection Pattern

FastAPI's dependency injection provides clean separation:

```python
# Reusable dependencies
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

# Usage in routes
@router.post("/annotations/")
async def create_annotation(
    annotation_data: AnnotationCreate,
    db: DatabaseSession,  # Auto-injected database session
    current_user: CurrentUser,  # Auto-injected authenticated user
):
    # Business logic here
    pass
```

### Error Handling

Centralized error handling with appropriate HTTP status codes:

```python
# Authentication errors
raise HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid authentication credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

# Authorization errors
raise HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Admin privileges required",
)

# Not found errors
raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Screenshot not found",
)

# Validation errors (automatic via Pydantic)
# Returns HTTP 422 with detailed validation errors
```

---

## WebSocket Architecture

### Connection Lifecycle

```
Client                          Server
  │                               │
  │  WS /api/ws?token=<JWT>       │
  ├──────────────────────────────>│
  │                               │
  │      Verify JWT Token         │
  │◄──────────────────────────────┤
  │                               │
  │   Connection Accepted         │
  │◄──────────────────────────────┤
  │                               │
  │  user_joined (broadcast)      │
  │◄──────────────────────────────┤
  │                               │
  │       ping (every 30s)        │
  ├──────────────────────────────>│
  │                               │
  │         pong                  │
  │◄──────────────────────────────┤
  │                               │
  │    Event Broadcasts           │
  │◄──────────────────────────────┤
  │                               │
  │  WebSocketDisconnect          │
  │◄──────────────────────────────┤
  │                               │
  │  user_left (broadcast)        │
  │◄──────────────────────────────┤
  │                               │
```

### WebSocket Event Structure

All events follow a consistent structure:

```typescript
interface WebSocketEvent {
  type: string;           // Event type identifier
  timestamp: string;      // ISO 8601 timestamp
  data: {                 // Event-specific payload
    [key: string]: any;
  };
}
```

### Event Types and Payloads

#### 1. annotation_submitted

Triggered when a user submits an annotation.

```json
{
  "type": "annotation_submitted",
  "timestamp": "2025-01-15T10:30:45.123Z",
  "data": {
    "screenshot_id": 42,
    "user_id": 7,
    "username": "alice",
    "annotation_count": 2,
    "required_count": 3,
    "has_consensus": false
  }
}
```

#### 2. screenshot_completed

Triggered when a screenshot reaches required annotation count.

```json
{
  "type": "screenshot_completed",
  "timestamp": "2025-01-15T10:35:22.456Z",
  "data": {
    "screenshot_id": 42,
    "filename": "screenshot_20250115.png",
    "annotation_count": 3
  }
}
```

#### 3. consensus_disputed

Triggered when disagreements are detected.

```json
{
  "type": "consensus_disputed",
  "timestamp": "2025-01-15T10:35:23.789Z",
  "data": {
    "screenshot_id": 42,
    "filename": "screenshot_20250115.png",
    "disagreement_count": 5
  }
}
```

#### 4. user_joined / user_left

Triggered on user connection/disconnection.

```json
{
  "type": "user_joined",  // or "user_left"
  "timestamp": "2025-01-15T10:25:00.000Z",
  "data": {
    "user_id": 7,
    "username": "alice",
    "active_users": 4
  }
}
```

### Frontend WebSocket Client

**Features**:
- Automatic reconnection with exponential backoff
- Message queuing during disconnection
- Heartbeat ping/pong (30s interval)
- Event listener pattern (on/off)
- Type-safe event handlers

**Reconnection Strategy**:

```typescript
// Exponential backoff: 1s, 2s, 4s, 8s, 16s (capped at 10s)
const delay = Math.min(
  this.reconnectDelay * Math.pow(2, this.reconnectAttempts),
  10000
);

// Max 5 reconnection attempts
if (this.reconnectAttempts < this.maxReconnectAttempts) {
  setTimeout(() => this.connect(token), delay);
}
```

---

## Consensus Algorithm

### Detailed Algorithm Flow

```
Input: screenshot_id, consensus_strategy (default: MEDIAN)

Step 1: Fetch all annotations for screenshot
  ↓
Step 2: Collect unique hours across all annotations
  ↓
Step 3: For each hour:
  │
  ├─> Collect values from all annotations
  │
  ├─> Calculate consensus value using strategy:
  │   ├─ MEDIAN: statistics.median(values)
  │   ├─ MEAN: statistics.mean(values)
  │   └─ MODE: statistics.mode(values) [fallback to median if no mode]
  │
  ├─> Calculate max difference: max(|value - consensus_value|)
  │
  ├─> Classify severity:
  │   ├─ max_diff == 0 → NONE
  │   ├─ max_diff <= 2 → MINOR
  │   ├─ max_diff <= 5 → MODERATE
  │   └─ max_diff > 5 → MAJOR
  │
  └─> If max_diff > 5 (threshold):
      Add to disagreements list
  ↓
Step 4: Determine overall consensus:
  has_consensus = (len(disagreements) == 0)
  ↓
Step 5: Save/update ConsensusResult:
  ├─ has_consensus
  ├─ consensus_values (if has_consensus)
  └─ disagreement_details
  ↓
Step 6: Update screenshot.has_consensus
  ↓
Output: Consensus analysis result
```

### Example Consensus Calculation

**Input Data**:

```python
annotations = [
  {"hourly_values": {"0": 10.0, "1": 15.0, "2": 20.0}},  # User 1
  {"hourly_values": {"0": 12.0, "1": 14.0, "2": 21.0}},  # User 2
  {"hourly_values": {"0": 11.0, "1": 15.0, "2": 25.0}},  # User 3
]
```

**Processing**:

| Hour | Values | Median | Max Diff | Severity | Disagreement? |
|------|--------|--------|----------|----------|---------------|
| 0 | [10, 11, 12] | 11.0 | 2.0 | MINOR | No (≤5) |
| 1 | [14, 15, 15] | 15.0 | 1.0 | MINOR | No (≤5) |
| 2 | [20, 21, 25] | 21.0 | 5.0 | MODERATE | No (≤5) |

**Output**:

```json
{
  "screenshot_id": 1,
  "has_consensus": true,
  "has_disagreements": false,
  "total_annotations": 3,
  "disagreements": [],
  "consensus_hourly_values": {
    "0": 11.0,
    "1": 15.0,
    "2": 21.0
  },
  "strategy_used": "median"
}
```

**If Hour 2 had values [20, 21, 30]**:

| Hour | Values | Median | Max Diff | Severity | Disagreement? |
|------|--------|--------|----------|----------|---------------|
| 2 | [20, 21, 30] | 21.0 | 10.0 | MAJOR | Yes (>5) |

Output would include:

```json
{
  "has_consensus": false,
  "has_disagreements": true,
  "disagreements": [
    {
      "hour": "2",
      "values": [20.0, 21.0, 30.0],
      "consensus_value": 21.0,
      "has_disagreement": true,
      "max_difference": 10.0,
      "severity": "major",
      "strategy_used": "median"
    }
  ]
}
```

---

## Security Model

### Authentication Flow

```
1. User Registration:
   ├─ Password hashed with bcrypt (salt rounds: 12)
   ├─ Stored as hashed_password in database
   └─ Never store plain text password

2. User Login:
   ├─ Verify username exists
   ├─ Compare password hash: bcrypt.verify(password, stored_hash)
   ├─ Generate JWT token with payload:
   │  {
   │    "sub": user_id,
   │    "username": username,
   │    "role": role,
   │    "exp": expiration_timestamp
   │  }
   └─ Return access_token to client

3. Protected Route Access:
   ├─ Extract token from Authorization header: "Bearer <token>"
   ├─ Verify token signature with SECRET_KEY
   ├─ Check expiration (default: 30 minutes)
   ├─ Extract user_id from payload
   ├─ Load User from database
   └─ Inject user into route handler dependency
```

### Authorization Levels

| Role | Permissions |
|------|-------------|
| **annotator** | - View assigned screenshots<br>- Submit annotations<br>- View own annotation history<br>- Update own annotations<br>- Access consensus data for reviewed screenshots |
| **admin** | - All annotator permissions<br>- Upload screenshots<br>- View all users<br>- Activate/deactivate users<br>- Promote users to admin<br>- Export consensus data<br>- View disputed screenshots<br>- Access comprehensive statistics |

### WebSocket Security

```python
async def websocket_endpoint(websocket: WebSocket, token: str | None = None):
    # 1. Validate token presence
    if not token:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Missing authentication token"
        )
        return

    # 2. Verify JWT
    user_data = await verify_websocket_token(token)
    if not user_data:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid authentication token"
        )
        return

    # 3. Accept connection
    await manager.connect(websocket, user_data["user_id"], user_data["username"])
```

### CORS Configuration

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Frontend dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Production**: Replace with specific production domain(s)

### SQL Injection Prevention

All database queries use SQLAlchemy ORM or parameterized queries:

```python
# Safe: ORM query
stmt = select(User).where(User.username == username)

# Safe: Parameterized query
stmt = text("SELECT * FROM users WHERE username = :username")
result = await db.execute(stmt, {"username": username})
```

---

## Data Flow

### Complete Annotation Workflow

```
1. Admin Uploads Screenshot
   ├─ POST /api/admin/screenshots/upload
   ├─ Save file to uploads/screenshots/
   ├─ Create Screenshot record (status: pending)
   └─ Broadcast event (optional)

2. Annotator Requests Assignment
   ├─ GET /api/screenshots/next
   ├─ Query pending screenshots
   ├─ Exclude already annotated by user
   ├─ Return screenshot with lowest annotation_count
   └─ (No database modification)

3. Auto-Processing (Client-Side or Server-Side)
   ├─ Load screenshot image
   ├─ Detect grid boundaries (OCR-based)
   ├─ Extract hourly values
   └─ Return pre-filled data to client

4. Annotator Submits Annotation
   ├─ POST /api/annotations/
   ├─ Validate data (Pydantic schema)
   ├─ Check user hasn't already annotated
   ├─ Create Annotation record
   ├─ Increment screenshot.current_annotation_count
   ├─ If count >= required_annotations:
   │  └─ Update screenshot.status = "completed"
   ├─ Broadcast "annotation_submitted" event (WebSocket)
   └─ Return created annotation

5. Consensus Analysis (If >= 2 Annotations)
   ├─ Triggered automatically after annotation submission
   ├─ Fetch all annotations for screenshot
   ├─ Calculate consensus values (median/mean/mode)
   ├─ Detect disagreements (max_diff > threshold)
   ├─ Classify severity (minor/moderate/major)
   ├─ Save/update ConsensusResult record
   ├─ Update screenshot.has_consensus
   ├─ If disagreements found:
   │  └─ Broadcast "consensus_disputed" event
   └─ Return consensus analysis

6. Screenshot Completion
   ├─ If screenshot.current_annotation_count == required_annotations
   ├─ Update screenshot.status = "completed"
   └─ Broadcast "screenshot_completed" event

7. Admin Reviews Disputed Screenshots
   ├─ GET /api/admin/disputed
   ├─ Query screenshots with has_consensus = False
   ├─ Join ConsensusResult for disagreement details
   └─ Display in disagreement heatmap

8. Admin Exports Data
   ├─ GET /api/admin/export/consensus
   ├─ Query all completed screenshots with consensus
   ├─ Generate CSV with hourly values
   └─ Stream CSV download to client
```

---

## Performance Considerations

### Database Optimization

1. **Indexing Strategy**:
   ```sql
   CREATE INDEX idx_screenshots_status ON screenshots(status);
   CREATE INDEX idx_screenshots_user_assignment ON screenshots(current_annotation_count, status);
   CREATE INDEX idx_annotations_screenshot ON annotations(screenshot_id);
   CREATE INDEX idx_annotations_user ON annotations(user_id);
   CREATE UNIQUE INDEX idx_annotations_unique ON annotations(screenshot_id, user_id);
   CREATE INDEX idx_consensus_screenshot ON consensus_results(screenshot_id);
   ```

2. **Async Database Operations**:
   - All queries use `asyncpg` driver
   - Non-blocking I/O for concurrent requests
   - Connection pooling via SQLAlchemy

3. **Query Optimization**:
   - Use `selectinload()` to prevent N+1 queries
   - Limit result sets with pagination
   - Avoid SELECT * queries

### WebSocket Scalability

1. **Connection Limits**:
   - Single uvicorn worker: ~1000 concurrent connections
   - Horizontal scaling: Use Redis pub/sub for cross-server broadcasts

2. **Memory Management**:
   - Active connections stored in memory (`dict`)
   - Automatic cleanup on disconnect
   - Heartbeat ensures stale connections are removed

3. **Event Broadcasting**:
   - O(n) complexity for broadcast (n = active connections)
   - Error handling prevents cascade failures
   - Failed sends trigger automatic cleanup

### Frontend Optimization

1. **Code Splitting**:
   - Lazy load pages with `React.lazy()`
   - Reduce initial bundle size

2. **State Management**:
   - Zustand for minimal re-renders
   - Selective subscriptions to prevent unnecessary updates

3. **Image Loading**:
   - Lazy load screenshot images
   - Use thumbnails for lists
   - Full resolution only on detail view

### Caching Strategy

**Backend**:
- No caching layer currently (PostgreSQL query cache sufficient)
- Future: Redis for session storage and pub/sub

**Frontend**:
- Axios response caching via interceptors
- React Query for server state management (future)

---

## Deployment Architecture

### Production Setup

```
┌───────────────────────────────────────────────────┐
│                    Internet                        │
└─────────────────────┬─────────────────────────────┘
                      │
                      ▼
            ┌─────────────────┐
            │  Nginx (443)    │  (Reverse Proxy + SSL)
            └────────┬────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
         ▼                       ▼
┌─────────────────┐    ┌─────────────────┐
│  Static Files   │    │  Backend API    │
│  (React Build)  │    │  (Uvicorn)      │
│  Port 80        │    │  Port 8000      │
└─────────────────┘    └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │  PostgreSQL     │
                       │  Port 5432      │
                       └─────────────────┘
```

**See**: `DEPLOYMENT.md` for detailed production deployment instructions

---

## Future Enhancements

1. **Horizontal Scaling**:
   - Redis pub/sub for WebSocket broadcasts across multiple servers
   - Load balancer (HAProxy/Nginx) for API servers
   - Read replicas for PostgreSQL

2. **Advanced Analytics**:
   - User accuracy scoring over time
   - Screenshot difficulty classification
   - Annotation time heatmaps

3. **Machine Learning Integration**:
   - Train ML model on consensus annotations
   - Auto-suggest values based on trained model
   - Confidence scores for predictions

4. **Enhanced Admin Tools**:
   - Bulk screenshot re-annotation
   - Manual consensus override
   - Annotation quality scoring
   - User performance dashboards

5. **Audit Logging**:
   - Track all admin actions
   - Annotation edit history
   - Data export audit trail

6. **Mobile App**:
   - Native iOS/Android apps
   - Offline annotation capability
   - Push notifications for assignments

---

## Technology Decisions

### Why FastAPI?

- **Async-first**: Native async/await support for high concurrency
- **OpenAPI**: Automatic API documentation
- **Pydantic**: Built-in data validation and serialization
- **WebSocket**: Built-in WebSocket support
- **Performance**: Comparable to Node.js and Go

### Why PostgreSQL?

- **ACID Compliance**: Data integrity for collaborative annotations
- **JSONB**: Flexible storage for hourly_values
- **Async Support**: Compatible with asyncpg
- **Mature**: Battle-tested in production environments

### Why React + TypeScript?

- **Type Safety**: Catch errors at compile time
- **Component Reusability**: DRY principle
- **Large Ecosystem**: Abundant libraries and tools
- **Developer Experience**: Hot Module Replacement (HMR)

### Why Zustand over Redux?

- **Simplicity**: Less boilerplate
- **Performance**: Minimal re-renders
- **Small Bundle**: ~3KB vs 40KB+ for Redux Toolkit
- **Sufficient**: No need for Redux's advanced features

---

## Conclusion

This architecture provides:

- **Scalability**: Async backend, horizontal scaling capability
- **Reliability**: ACID transactions, automatic reconnection
- **Security**: JWT auth, role-based access, SQL injection prevention
- **Real-Time**: WebSocket for live updates
- **Maintainability**: Clear separation of concerns, comprehensive testing
- **Developer Experience**: Type safety, automatic API docs, hot reload

The system is designed for research-grade data collection with multi-user collaboration and consensus validation.
