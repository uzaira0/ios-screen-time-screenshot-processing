# Scripts

Utility scripts for development, testing, and deployment.

## Startup Scripts

### Backend
- `start-backend.sh` - Start FastAPI backend server (Unix/Linux/macOS)
- `start-backend.bat` - Start FastAPI backend server (Windows)

### Frontend
- `start-frontend.sh` - Start React development server (Unix/Linux/macOS)
- `start-frontend.bat` - Start React development server (Windows)

## Utility Scripts

- `benchmark_backend.py` - Benchmark the backend processing pipeline
- `verify_structure.py` - Verify project structure without dependencies

## Docker Scripts

- `verify_docker.sh` - Verify Docker deployment
- `test_phases_in_docker.py` - Test implementation phases in Docker
- `test_advanced_integration.py` - Advanced integration tests

## Usage

### Starting Development Servers

**Unix/Linux/macOS:**
```bash
./scripts/start-backend.sh   # Start backend on port 8000
./scripts/start-frontend.sh  # Start frontend on port 5173
```

**Windows:**
```cmd
scripts\start-backend.bat
scripts\start-frontend.bat
```

### Running Benchmarks

```bash
python scripts/benchmark_backend.py
```

### Verifying Structure

```bash
python scripts/verify_structure.py
```
