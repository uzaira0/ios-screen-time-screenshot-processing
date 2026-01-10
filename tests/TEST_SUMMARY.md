# Comprehensive Backend Test Suite Summary

## Overview

This document describes the comprehensive test suite for the screenshot annotator backend. The suite includes unit tests, integration tests, and end-to-end tests covering all critical workflows and edge cases.

## Test Structure

```
tests/
├── unit/                          # Unit tests (isolated component testing)
│   ├── test_schemas.py           # Pydantic schema validation tests
│   ├── test_models.py            # SQLAlchemy model tests
│   └── test_services.py          # Service layer business logic tests
│
├── integration/                   # Integration tests (API endpoint testing)
│   ├── conftest.py               # Shared fixtures for integration tests
│   ├── test_annotation_workflow.py  # Existing annotation tests
│   ├── test_upload_workflow.py   # Upload API tests
│   ├── test_queue_workflow.py    # Queue and filtering tests
│   ├── test_consensus_workflow.py # Consensus calculation tests
│   ├── test_export_workflow.py   # JSON/CSV export tests
│   ├── test_admin_workflow.py    # Admin-only endpoint tests
│   └── test_stats_workflow.py    # Statistics endpoint tests
│
└── e2e/                          # End-to-end tests (complete workflows)
    ├── conftest.py               # E2E-specific fixtures
    ├── test_complete_workflow.py # Full pipeline simulations
    ├── test_concurrent_annotation.py # Concurrency and race conditions
    └── test_error_recovery.py    # Error handling and recovery
```

## Test Coverage

### Unit Tests (tests/unit/)

#### test_schemas.py
- **Schema Validation**: Tests all Pydantic schemas with valid and invalid data
- **Field Constraints**: Tests min_length, max_length, ge/le validators
- **Grid Coordinate Validation**: Tests negative values, missing x/y keys
- **Image Type Validation**: Parametrized tests for battery/screen_time patterns
- **Coverage**: 40+ tests covering AnnotationBase, ScreenshotCreate, UserCreate, UploadRequest, etc.

#### test_models.py
- **Model Creation**: Tests default values, nullable fields, enum types
- **Relationships**: Tests User->Annotations, Screenshot->Group, cascade deletes
- **Constraints**: Tests unique constraints (username, screenshot_id+user_id)
- **JSON Fields**: Tests extracted_hourly_data, processing_issues, verified_by_user_ids
- **Coverage**: 50+ tests covering all database models

#### test_services.py
- **ConsensusService**: Tests median/mean/mode strategies, disagreement severity classification
- **QueueService**: Tests queue filtering, user exclusions, skip operations
- **Business Logic**: Tests consensus calculation with 2-3 annotations, queue stats
- **Coverage**: 30+ tests covering service layer logic

**Total Unit Tests**: ~120 tests

### Integration Tests (tests/integration/)

#### test_upload_workflow.py
- Upload with all metadata fields (participant_id, group_id, device_type, etc.)
- Upload with minimal required fields
- API key validation (valid, invalid, missing)
- Base64 image validation (invalid data, unsupported formats)
- Group auto-creation on first upload
- Duplicate detection by file hash
- Device type auto-detection
- Celery task triggering
- **Coverage**: 15+ tests

#### test_queue_workflow.py
- Get next screenshot from queue
- Empty queue handling
- Filtering by group_id, processing_status
- Skip screenshot functionality
- Disputed screenshots queue
- Paginated screenshot list with filters
- **Coverage**: 10+ tests

#### test_consensus_workflow.py
- Full agreement between annotators
- Disagreement detection and severity classification
- Three-annotator median calculation
- Consensus recalculation after new annotation
- Handling missing hours in annotations
- Screenshot.has_consensus flag updates
- **Coverage**: 10+ tests

#### test_export_workflow.py
- JSON export structure and all fields
- JSON export with group filter
- JSON export includes consensus data
- CSV export format and headers
- CSV export with group filter
- CSV consensus values in correct columns
- Empty export handling
- **Coverage**: 10+ tests

#### test_admin_workflow.py
- Get all users with stats (admin only)
- Non-admin access forbidden
- Update user role
- Deactivate user
- Invalid role validation
- Nonexistent user handling
- Unauthorized operations
- **Coverage**: 10+ tests

#### test_stats_workflow.py
- All stats fields present
- Stats update after upload
- Stats update after annotation
- Processing status counts
- Consensus/disagreement counts
- Average annotations calculation
- Empty database handling
- **Coverage**: 10+ tests

**Total Integration Tests**: ~65 tests

### End-to-End Tests (tests/e2e/)

#### test_complete_workflow.py
- **Full Pipeline**: Upload → Auto-process → Multi-user annotation → Consensus → Export
- **Multi-user Redundancy**: Multiple screenshots, 2 annotations each, consensus for all
- **Annotation Correction**: User updates own annotation via upsert
- **Skip and Disputed**: User skips, others create disagreement, disputed queue
- **Batch Upload**: Multiple screenshots, group creation, queue stats
- **Coverage**: 5 comprehensive workflow tests

#### test_concurrent_annotation.py
- Concurrent annotations from different users
- Annotation count updates under concurrent load
- Concurrent consensus calculation
- Concurrent queue access
- Concurrent skip operations
- Concurrent upsert (same user)
- Race condition at target_annotations threshold
- **Coverage**: 8 concurrency tests

#### test_error_recovery.py
- Invalid screenshot_id
- Malformed annotation data
- Invalid grid coordinates
- Missing authentication
- Annotation deletion rollback
- Unauthorized deletion
- Nonexistent screenshot operations
- Empty hourly_values handling
- Database transaction rollback
- Export with no data
- Invalid pagination parameters
- Recovery from failed processing
- **Coverage**: 15+ error scenarios

**Total E2E Tests**: ~28 tests

## Grand Total: ~213 Comprehensive Tests

## Running Tests

### Run All Tests
```bash
pytest tests/ -v
```

### Run Specific Test Suites
```bash
# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# E2E tests only
pytest tests/e2e/ -v

# Specific test file
pytest tests/unit/test_schemas.py -v

# Specific test class or function
pytest tests/integration/test_upload_workflow.py::TestScreenshotUpload::test_upload_with_all_metadata -v
```

### Run with Coverage Report
```bash
pytest tests/ --cov=screenshot_processor --cov-report=html
```

### Run Tests in Parallel (Faster)
```bash
pytest tests/ -n auto
```

## Key Testing Patterns Used

### 1. Async Testing with pytest-asyncio
```python
@pytest.mark.asyncio
async def test_example(client: AsyncClient, db_session: AsyncSession):
    response = await client.get("/api/endpoint")
    assert response.status_code == 200
```

### 2. Fixture-Based Test Data
```python
@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(username="testuser", role="annotator", is_active=True)
    db_session.add(user)
    await db_session.commit()
    return user
```

### 3. Mocking External Dependencies
```python
@pytest.fixture(autouse=True)
def mock_celery_task(self):
    with patch("screenshot_processor.web.tasks.process_screenshot_task") as mock:
        yield mock
```

### 4. Parametrized Tests
```python
@pytest.mark.parametrize("image_type,expected_valid", [
    ("screen_time", True),
    ("battery", True),
    ("invalid", False),
])
def test_image_type_validation(image_type, expected_valid):
    # Test implementation
```

### 5. Database Isolation
- Each test gets fresh in-memory SQLite database
- Tables created before test, dropped after
- No test pollution or shared state

## Critical Workflows Tested

### 1. Upload Pipeline
✅ API upload with metadata  
✅ Group auto-creation  
✅ Device type detection  
✅ Duplicate detection  
✅ Background processing trigger  
✅ Validation and error handling  

### 2. Annotation Workflow
✅ Single user annotation  
✅ Multi-user redundancy  
✅ Annotation upsert (corrections)  
✅ Queue management  
✅ Skip functionality  
✅ Concurrent annotations  

### 3. Consensus System
✅ Agreement detection  
✅ Disagreement detection  
✅ Median/mean/mode strategies  
✅ Severity classification  
✅ Recalculation on updates  
✅ Multi-annotator scenarios  

### 4. Export Functionality
✅ JSON export with all fields  
✅ CSV export with consensus  
✅ Group filtering  
✅ Empty data handling  
✅ Timestamp tracking  

### 5. Admin Functions
✅ User management  
✅ Role updates  
✅ User activation/deactivation  
✅ Access control (403 for non-admins)  
✅ Statistics tracking  

### 6. Error Handling
✅ Invalid inputs  
✅ Missing authentication  
✅ Nonexistent resources  
✅ Database rollback  
✅ Concurrent conflicts  
✅ Recovery from failures  

## Mocked Dependencies

To enable fast, isolated testing, the following external dependencies are mocked:

1. **Celery Tasks**: `process_screenshot_task.delay()` - Mocked to prevent actual background processing
2. **File System**: Upload directory mocked to prevent actual file writes during tests
3. **API Keys**: Test API key configured via mock settings
4. **OpenCV/Tesseract**: Processing functions mocked in upload tests

## Test Data Fixtures

### Standard Fixtures (tests/integration/conftest.py)
- `db_session`: Fresh async database session
- `client`: AsyncClient with dependency injection
- `test_user`: Standard annotator user
- `test_admin`: Admin user
- `test_screenshot`: Single screenshot for testing
- `multiple_users`: 3 annotator users
- `test_group`: Group with id="test_group"
- `multiple_screenshots`: 5 screenshots in test_group
- `auth_headers(username)`: Helper for X-Username authentication

### E2E-Specific Fixtures (tests/e2e/conftest.py)
- Extended versions of integration fixtures for complex scenarios

## Assertions and Verifications

Tests verify:
- HTTP status codes (200, 201, 204, 400, 403, 404, 422, 500)
- Response JSON structure and fields
- Database state after operations
- Relationship integrity (foreign keys, cascades)
- Business rule enforcement (consensus thresholds, annotation counts)
- Concurrent operation safety
- Transaction rollback on errors

## Known Limitations

1. **No WebSocket Testing**: WebSocket events are triggered but not verified (requires WebSocket test client)
2. **No Actual File I/O**: Files are mocked to avoid filesystem dependency
3. **No Actual OCR**: Tesseract processing is mocked in most tests
4. **In-Memory Database**: SQLite in-memory may not catch PostgreSQL-specific issues
5. **No Performance Testing**: Load testing and performance benchmarks not included

## Future Enhancements

- [ ] Add WebSocket event verification
- [ ] Add Playwright E2E tests for frontend integration
- [ ] Add load/performance tests with Locust
- [ ] Add mutation testing to verify test quality
- [ ] Add visual regression tests for rendered outputs
- [ ] Add database migration tests with Alembic
- [ ] Add contract testing for API versioning
- [ ] Increase coverage to 95%+ across all modules

## Production Readiness

This test suite provides:
- ✅ Comprehensive coverage of all API endpoints
- ✅ Validation of business logic and data integrity
- ✅ Concurrency and race condition testing
- ✅ Error handling and recovery validation
- ✅ Multi-user workflow verification
- ✅ Regression protection for future changes

**Confidence Level**: HIGH - Ready for production deployment with these tests passing.

## Running Tests in CI/CD

Example GitHub Actions workflow:

```yaml
- name: Run tests
  run: |
    pytest tests/ -v --cov=screenshot_processor --cov-report=xml
    
- name: Upload coverage
  uses: codecov/codecov-action@v3
  with:
    file: ./coverage.xml
```

## Contact

For questions about the test suite, see:
- `tests/integration/conftest.py` - Fixture documentation
- Individual test files - Inline comments and docstrings
- `CLAUDE.md` - Project architecture overview
