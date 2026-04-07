# Deployment Guide

Comprehensive guide for deploying monorepo packages to remote servers with GitHub Actions, Docker Compose, and optional Traefik reverse proxy.

---

## Overview

This guide covers deploying a package from a monorepo to a standalone remote server using:

- **Git subtree push** for clean deployment without monorepo path prefixes
- **GitHub Actions** with self-hosted runner for auto-deployment on push
- **GitHub Container Registry (GHCR)** for pre-built Docker images (faster deploys)
- **GitHub Environments** for deployment approvals and secrets
- **Docker Compose** for multi-container production stack (Postgres, Redis, backend, frontend)
- **Traefik** reverse proxy for path-based routing (optional, for multi-app servers)
- **OpenAPI/Pydantic** as single source of truth for frontend-backend contracts
- **Vite environment variables** for configurable API paths

### Architecture Options

**Option A: GHCR + Direct Port Access** (Recommended for single-app servers)
```
┌─────────────────────────────────────────────────────────────────────┐
│                         GitHub                                       │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────────┐    │
│  │ Git Subtree │───▶│  Build Job   │───▶│  Push to GHCR       │    │
│  │   Push      │    │(ubuntu-latest)    │ (ghcr.io/org/app)   │    │
│  └─────────────┘    └──────────────┘    └─────────────────────┘    │
│                                                   │                  │
│                            ┌──────────────────────┘                  │
│                            ▼                                         │
│                    ┌───────────────┐                                │
│                    │ Environment   │                                │
│                    │ Approval Gate │                                │
│                    └───────────────┘                                │
│                            │                                         │
└────────────────────────────┼─────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Your Local Network                                │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Self-Hosted Runner → Pull images → docker compose up         │  │
│  │                                                                │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐      │  │
│  │  │ Postgres │ │  Redis   │ │ Backend  │ │  Frontend   │      │  │
│  │  │  :5432   │ │  :6379   │ │  :8002   │ │   :3002     │      │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └─────────────┘      │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

**Option B: Traefik Path-Based Routing** (For multi-app servers)
```
Internet → Traefik (port 80/443)
    ↓ PathPrefix routing
├── /screenshot/api/* → screenshot-backend (8002) [priority 2]
├── /screenshot/*     → screenshot-frontend (80)  [priority 1]
├── /flash/api/*      → flash-backend (8001)      [priority 2]
└── /flash/*          → flash-frontend (80)       [priority 1]
```

---

## 1. Git Subtree Push (CRITICAL for Monorepo)

### Problem

When a package lives in a monorepo (e.g., `apps/screenshot-annotator/`), pushing directly from inside that folder includes the monorepo path prefix in all file paths, breaking the standalone deployment.

### Wrong Approach

```bash
# NEVER do this from inside a package folder
cd apps/screenshot-annotator
git push screenshot-annotator-standalone HEAD:main  # BROKEN!
# Results in paths like: apps/screenshot-annotator/src/... on the remote
```

### Correct Approach

```bash
# ALWAYS use git subtree from monorepo root
cd /path/to/monorepo

# Normal push
git subtree push --prefix=apps/screenshot-annotator screenshot-annotator-standalone main

# If subtree push fails (non-fast-forward), split and force push:
git subtree split --prefix=apps/screenshot-annotator -b temp-split
git push screenshot-annotator-standalone temp-split:main --force
git branch -D temp-split
```

### Setup Remote Once

```bash
# Add the standalone repo as a remote
git remote add screenshot-annotator-standalone git@github.com:user/screenshot-annotator.git
```

### Standalone Repos Reference

| Package | Remote Name | GitHub Repo |
|---------|-------------|-------------|
| `apps/screenshot-annotator` | `screenshot-annotator-standalone` | `uzaira0/screenshot-annotator` |
| `packages/flash-processing` | `flash-processing-standalone` | `uzaira0/flash-processing` |

---

## 2. Self-Hosted Runner Setup

### 2.1 Create Runner on GitHub

1. Go to your **standalone** repository **Settings → Actions → Runners**
2. Click **New self-hosted runner**
3. Select **Linux** and your architecture (x64, ARM64)
4. Follow the download instructions shown

### 2.2 Install Runner on Server

```bash
# SSH into your server
ssh user@your-server

# Create directory for runner
mkdir -p /opt/actions-runner && cd /opt/actions-runner

# Download runner (check GitHub for latest version)
curl -o actions-runner-linux-x64-2.311.0.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-linux-x64-2.311.0.tar.gz
tar xzf ./actions-runner-linux-x64-2.311.0.tar.gz

# Configure (get token from GitHub repo Settings → Actions → Runners)
./config.sh --url https://github.com/user/screenshot-annotator --token YOUR_TOKEN

# Install as service
sudo ./svc.sh install
sudo ./svc.sh start

# Verify status
sudo ./svc.sh status
```

### 2.3 Runner Requirements

The runner user needs:
- Docker group membership: `sudo usermod -aG docker $USER`
- Read access to `/opt/screenshot-annotator/docker/.env`

### 2.4 Troubleshooting Runner Service

**Error 203/EXEC when running as service:**
```bash
# Check shebang in runsvc.sh
head -1 /opt/actions-runner/runsvc.sh

# Verify bash location
which bash

# If mismatch, edit service file to use explicit bash path
sudo nano /etc/systemd/system/actions.runner.*.service
# Change: ExecStart=/opt/actions-runner/runsvc.sh
# To:     ExecStart=/usr/bin/bash /opt/actions-runner/runsvc.sh

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart actions.runner.*.service
```

**SELinux issues (RedHat/CentOS):**
```bash
# Check if SELinux is blocking
getenforce

# Allow execution
sudo chcon -R -t bin_t /opt/actions-runner/
```

---

## 3. Docker Configuration

### 3.1 Project Structure

```
project/
├── .github/
│   └── workflows/
│       └── deploy.yml          # GitHub Actions workflow
├── docker/
│   ├── docker-compose.yml      # Production stack
│   ├── backend/
│   │   └── Dockerfile
│   ├── frontend/
│   │   └── Dockerfile
│   └── .env.production.example
├── frontend/
│   └── nginx.conf
├── scripts/
│   └── deploy.sh               # Server-side deployment script
├── src/
│   └── app_name/
└── pyproject.toml
```

### 3.2 Docker Compose with GHCR Support

Modify `docker-compose.yml` to support both local builds and registry pulls:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: screenshot-postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-screenshot}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?required}
      POSTGRES_DB: ${POSTGRES_DB:-screenshot_annotations}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-screenshot}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - internal
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    container_name: screenshot-redis
    volumes:
      - redis_data:/data
    networks:
      - internal
    restart: unless-stopped

  backend:
    image: ${BACKEND_IMAGE:-}  # Empty default = use build
    build:
      context: ..
      dockerfile: docker/backend/Dockerfile
    container_name: screenshot-backend
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-screenshot}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-screenshot_annotations}
      SECRET_KEY: ${SECRET_KEY:?required}
      UPLOAD_API_KEY: ${UPLOAD_API_KEY:?required}
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "8002:8002"
    networks:
      - internal
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8002/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    image: ${FRONTEND_IMAGE:-}
    build:
      context: ../frontend
      dockerfile: Dockerfile
      args:
        VITE_API_BASE_URL: ${VITE_API_BASE_URL:-/api/v1}
    container_name: screenshot-frontend
    ports:
      - "3002:80"
    networks:
      - internal
    restart: unless-stopped

networks:
  internal:

volumes:
  postgres_data:
    name: screenshot_postgres_data
  redis_data:
    name: screenshot_redis_data
```

### 3.3 Production Environment Template

Create `docker/.env.production.example`:

```bash
# =============================================================================
# Production Environment Configuration
# =============================================================================
# Copy to .env and fill in real values. NEVER commit .env!

# Database
POSTGRES_USER=screenshot
POSTGRES_PASSWORD=CHANGE_ME_GENERATE_SECURE_PASSWORD
POSTGRES_DB=screenshot_annotations

# Application Security
SECRET_KEY=CHANGE_ME_64_HEX_CHARACTERS
UPLOAD_API_KEY=CHANGE_ME_SECURE_API_KEY

# Frontend (for builds)
VITE_API_BASE_URL=/api/v1

# Docker Images (set by CI/CD, don't change manually)
# BACKEND_IMAGE=ghcr.io/your-org/screenshot-annotator-backend:latest
# FRONTEND_IMAGE=ghcr.io/your-org/screenshot-annotator-frontend:latest
```

---

## 4. GitHub Actions Workflow

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Production

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      skip_build:
        description: 'Skip build and use existing images'
        required: false
        default: 'false'
        type: boolean

permissions:
  contents: read
  packages: write

concurrency:
  group: production-deploy
  cancel-in-progress: false

env:
  REGISTRY: ghcr.io
  IMAGE_PREFIX: ${{ github.repository }}

jobs:
  # ===========================================================================
  # Build Docker Images (runs on GitHub's servers - fast, cached)
  # ===========================================================================
  build:
    name: Build Images
    runs-on: ubuntu-latest
    if: ${{ github.event.inputs.skip_build != 'true' }}
    outputs:
      image_tag: ${{ steps.version.outputs.tag }}

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set version tag
        id: version
        run: echo "tag=${{ github.sha }}" >> $GITHUB_OUTPUT

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push Backend
        uses: docker/build-push-action@v5
        with:
          context: .
          file: docker/backend/Dockerfile
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}-backend:${{ steps.version.outputs.tag }}
            ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}-backend:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Build and push Frontend
        uses: docker/build-push-action@v5
        with:
          context: ./frontend
          file: frontend/Dockerfile
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}-frontend:${{ steps.version.outputs.tag }}
            ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}-frontend:latest
          build-args: |
            VITE_API_BASE_URL=/api/v1
          cache-from: type=gha
          cache-to: type=gha,mode=max

  # ===========================================================================
  # Deploy (runs on your self-hosted runner)
  # ===========================================================================
  deploy:
    name: Deploy to Server
    needs: [build]
    if: ${{ always() && (needs.build.result == 'success' || github.event.inputs.skip_build == 'true') }}
    runs-on: self-hosted

    environment:
      name: production
      url: ${{ secrets.APP_URL }}

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Determine image tag
        id: tag
        run: |
          if [ "${{ github.event.inputs.skip_build }}" == "true" ]; then
            echo "tag=latest" >> $GITHUB_OUTPUT
          else
            echo "tag=${{ github.sha }}" >> $GITHUB_OUTPUT
          fi

      - name: Login to GitHub Container Registry
        run: |
          echo "${{ secrets.GITHUB_TOKEN }}" | docker login ghcr.io -u ${{ github.actor }} --password-stdin

      - name: Deploy application
        run: |
          set -e
          export IMAGE_TAG="${{ steps.tag.outputs.tag }}"
          export GITHUB_REPOSITORY="${{ github.repository }}"
          export APP_DIR="${APP_DIR:-/opt/screenshot-annotator}"
          "${APP_DIR}/scripts/deploy.sh"

      - name: Health check
        run: |
          sleep 30
          HEALTH_URL="${HEALTH_URL:-http://localhost:8002/health}"
          for i in {1..10}; do
            if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
              echo "Health check passed"
              exit 0
            fi
            echo "Attempt $i/10 failed, retrying..."
            sleep 10
          done
          echo "Health check failed"
          exit 1
        env:
          HEALTH_URL: ${{ secrets.APP_URL }}/health
```

---

## 5. Deployment Script

Create `scripts/deploy.sh`:

```bash
#!/bin/bash
set -euo pipefail

# Configuration
APP_DIR="${APP_DIR:-/opt/screenshot-annotator}"
COMPOSE_FILE="${APP_DIR}/docker/docker-compose.yml"
IMAGE_TAG="${IMAGE_TAG:-latest}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

# Check prerequisites
check_prerequisites() {
    command -v docker >/dev/null || { log "ERROR: Docker not installed"; exit 1; }
    docker compose version >/dev/null || { log "ERROR: Docker Compose not installed"; exit 1; }
    [ -f "$COMPOSE_FILE" ] || { log "ERROR: Compose file not found at $COMPOSE_FILE"; exit 1; }
    [ -f "${APP_DIR}/docker/.env" ] || { log "ERROR: .env file not found"; exit 1; }
}

# Pull images from registry
pull_images() {
    log "Pulling images with tag: ${IMAGE_TAG}..."
    cd "${APP_DIR}/docker"

    export BACKEND_IMAGE="ghcr.io/${GITHUB_REPOSITORY:-local}/screenshot-annotator-backend:${IMAGE_TAG}"
    export FRONTEND_IMAGE="ghcr.io/${GITHUB_REPOSITORY:-local}/screenshot-annotator-frontend:${IMAGE_TAG}"

    docker compose pull || log "WARNING: Pull failed, using local images"
}

# Restart services with minimal downtime
restart_services() {
    log "Restarting services..."
    cd "${APP_DIR}/docker"

    # Recreate app containers only (not database/redis)
    docker compose up -d --no-deps --force-recreate backend
    sleep 5
    docker compose up -d --no-deps --force-recreate celery-worker 2>/dev/null || true
    sleep 3
    docker compose up -d --no-deps --force-recreate frontend
}

# Run database migrations
run_migrations() {
    log "Running migrations..."
    cd "${APP_DIR}/docker"

    # Wait for database
    for i in {1..30}; do
        docker compose exec -T postgres pg_isready -U screenshot && break
        sleep 2
    done

    docker compose exec -T backend alembic upgrade head
}

# Health check
health_check() {
    log "Running health check..."
    for i in {1..10}; do
        if curl -sf http://localhost:8002/health > /dev/null; then
            log "Health check passed"
            return 0
        fi
        log "Attempt $i/10 failed, retrying..."
        sleep 5
    done
    log "ERROR: Health check failed"
    return 1
}

# Cleanup old images
cleanup() {
    log "Cleaning up old images..."
    docker image prune -f --filter "until=168h" 2>/dev/null || true
}

# Main
main() {
    log "=== Starting deployment ==="
    mkdir -p "${APP_DIR}/logs"

    check_prerequisites
    pull_images
    restart_services
    run_migrations
    health_check
    cleanup

    log "=== Deployment complete ==="
}

main "$@"
```

Make it executable:
```bash
chmod +x scripts/deploy.sh
```

---

## 6. GitHub Environment Setup

### 6.1 Create Environment

1. Go to **standalone** repository **Settings → Environments**
2. Click **New environment**
3. Name: `production`
4. Configure protection rules:
   - **Required reviewers**: Add yourself/team (optional)
   - **Wait timer**: Optional (e.g., 5 minutes)
   - **Deployment branches**: Select `main` only

### 6.2 Add Environment Secrets

| Secret | Description | Example |
|--------|-------------|---------|
| `APP_URL` | Your app's URL | `http://192.168.1.100:8002` |

**Note:** `GITHUB_TOKEN` is automatic - no need to add it.

---

## 7. Traefik Path-Based Routing (Optional)

Use this when deploying multiple apps on the same server.

### 7.1 Add Traefik Labels to docker-compose.yml

```yaml
services:
  backend:
    # ... existing config ...
    networks:
      - internal
      - traefik-local  # Add external network
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.screenshot-api.rule=PathPrefix(`/screenshot/api`)"
      - "traefik.http.services.screenshot-api.loadbalancer.server.port=8002"
      - "traefik.http.middlewares.screenshot-api-strip.stripprefix.prefixes=/screenshot"
      - "traefik.http.routers.screenshot-api.middlewares=screenshot-api-strip"
      - "traefik.http.routers.screenshot-api.priority=2"

  frontend:
    # ... existing config ...
    networks:
      - traefik-local
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.screenshot-fe.rule=PathPrefix(`/screenshot`)"
      - "traefik.http.services.screenshot-fe.loadbalancer.server.port=80"
      - "traefik.http.middlewares.screenshot-fe-strip.stripprefix.prefixes=/screenshot"
      - "traefik.http.routers.screenshot-fe.middlewares=screenshot-fe-strip"
      - "traefik.http.routers.screenshot-fe.priority=1"

networks:
  internal:
  traefik-local:
    external: true
```

### 7.2 Configure FastAPI Root Path

```python
import os
from fastapi import FastAPI

app = FastAPI(
    root_path=os.getenv("ROOT_PATH", ""),  # Set to "/screenshot" when behind Traefik
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
)
```

### 7.3 Update Frontend Build Args

```yaml
# In docker-compose.yml
frontend:
  build:
    args:
      VITE_API_BASE_URL: /screenshot/api/v1
      VITE_BASE_PATH: /screenshot
```

---

## 8. Type System (OpenAPI/Pydantic)

**The backend Pydantic schemas ARE the API contract.** The frontend generates TypeScript types from the OpenAPI spec.

### 8.1 Generate TypeScript Types

```bash
cd frontend
bun run generate:api-types
```

### 8.2 Workflow

1. Make API changes in backend (Pydantic models, endpoints)
2. Run `bun run generate:api-types` in frontend
3. TypeScript will flag any breaking changes

### 8.3 Usage Pattern

```typescript
// CORRECT - Import types from OpenAPI schema
import type { components } from "@/types/api-schema";
type ScreenshotRead = components["schemas"]["ScreenshotRead"];

// CORRECT - Use the typed apiClient
import { api } from "@/services/apiClient";
const screenshot = await api.screenshots.getScreenshot({ id: 123 });
```

**NEVER manually define TypeScript interfaces that mirror backend models.**

---

## 9. Vite Environment Variables

### 9.1 Define Types (vite-env.d.ts)

```typescript
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;   // API path: "/api/v1" or "/screenshot/api/v1"
  readonly VITE_BASE_PATH?: string;     // App prefix for Traefik: "/screenshot"
  readonly VITE_WS_URL?: string;        // WebSocket URL
}
```

### 9.2 Environment Files

```bash
# frontend/.env.development (local dev)
VITE_API_BASE_URL=http://localhost:8002/api/v1
VITE_WS_URL=ws://localhost:8002/api/v1/ws

# Production: Set via Dockerfile ARG, not .env file
```

---

## 10. Server Preparation

### 10.1 Create Application Directory

```bash
sudo mkdir -p /opt/screenshot-annotator
sudo chown $USER:$USER /opt/screenshot-annotator
cd /opt/screenshot-annotator
```

### 10.2 Clone Standalone Repository

```bash
git clone https://github.com/YOUR_ORG/screenshot-annotator.git .
```

### 10.3 Configure Environment

```bash
cp docker/.env.production.example docker/.env

# Generate secrets
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
echo "POSTGRES_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"

# Edit .env with generated values
nano docker/.env
```

### 10.4 Initial Deployment

```bash
cd /opt/screenshot-annotator/docker
docker compose up -d
docker compose logs -f  # Watch for errors
```

---

## 11. Security Best Practices

### Repository Security

- [ ] Repository is private
- [ ] Branch protection on `main` (require PR, approvals)
- [ ] Environment protection with required reviewers

### Server Security

- [ ] SSH key authentication only (no passwords)
- [ ] Firewall configured (only needed ports open)
- [ ] Dedicated deploy user with minimal permissions
- [ ] `.env` file not in version control
- [ ] `.env` file readable only by deploy user

### Secret Rotation Schedule

| Secret | Rotation Frequency |
|--------|-------------------|
| SSH keys | Every 90 days |
| Database password | Annually or after personnel changes |
| API keys | Annually |
| SECRET_KEY | After any suspected compromise |

---

## 12. Troubleshooting

### Git Subtree Push Fails

```bash
# Force push via split
git subtree split --prefix=apps/screenshot-annotator -b temp-split
git push screenshot-annotator-standalone temp-split:main --force
git branch -D temp-split
```

### Runner Not Picking Up Jobs

```bash
# Check runner status
sudo systemctl status actions.runner.*.service

# View runner logs
journalctl -u actions.runner.*.service -f

# Restart runner
cd /opt/actions-runner
sudo ./svc.sh restart
```

### Docker Login Fails

```bash
# Ensure runner user is in docker group
sudo usermod -aG docker $USER
# Log out and back in, or:
newgrp docker
```

### Images Not Pulling

```bash
# Check GHCR authentication
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Verify image exists
docker pull ghcr.io/your-org/screenshot-annotator-backend:latest
```

### Health Check Fails

```bash
# Check container status
docker compose ps

# View logs
docker compose logs backend --tail 100

# Check if port is accessible
curl -v http://localhost:8002/health
```

### 404 on API Calls (Traefik)

- Check `VITE_BASE_PATH` matches Traefik PathPrefix
- Verify stripprefix middleware is configured
- Check router priority (API should be higher than frontend)

### 405 Method Not Allowed

**Cause:** Server doesn't have the new code yet.
**Fix:** Deploy changes via git subtree push and wait for GitHub Actions.

### Container Won't Start

```bash
docker logs screenshot-backend
# Common: Missing env vars, port in use, health check failing
```

---

## 13. Deployment Checklist

### Initial Server Setup

- [ ] Install Docker and Docker Compose
- [ ] (Optional) Start Traefik: `cd /opt/traefik && docker-compose up -d`
- [ ] Create app directory: `mkdir -p /opt/screenshot-annotator`
- [ ] Clone standalone repo
- [ ] Create `.env` file with secrets
- [ ] Install GitHub Actions self-hosted runner
- [ ] Add runner user to docker group
- [ ] Initial `docker compose up -d`

### For Each Deploy

1. Commit all changes in monorepo
2. If API changed: regenerate TypeScript types (`bun run generate:api-types`)
3. Push via subtree: `git subtree push --prefix=apps/screenshot-annotator screenshot-annotator-standalone main`
4. GitHub Actions auto-deploys to server
5. Verify: `curl http://server:8002/health`

---

## 14. Quick Reference

### Commands Cheat Sheet

```bash
# Git subtree push
git subtree push --prefix=apps/screenshot-annotator screenshot-annotator-standalone main

# Force push (if subtree push fails)
git subtree split --prefix=apps/screenshot-annotator -b temp-split
git push screenshot-annotator-standalone temp-split:main --force
git branch -D temp-split

# Runner management
sudo ./svc.sh status|start|stop|install|uninstall

# Manual deployment on server
cd /opt/screenshot-annotator && IMAGE_TAG=latest ./scripts/deploy.sh

# View logs
docker compose logs -f
docker compose logs backend --tail 100

# Rollback to previous version
IMAGE_TAG=previous_sha ./scripts/deploy.sh

# Generate TypeScript types
cd frontend && bun run generate:api-types
```

### Files to Create/Modify

```
your-app/
├── .github/
│   └── workflows/
│       └── deploy.yml              # GitHub Actions workflow
├── docker/
│   ├── docker-compose.yml          # Add image: ${..._IMAGE:-} to services
│   ├── backend/
│   │   └── Dockerfile
│   ├── frontend/
│   │   └── Dockerfile
│   └── .env.production.example     # Production env template
├── scripts/
│   └── deploy.sh                   # Server-side deployment script
└── frontend/
    └── src/
        └── vite-env.d.ts           # Vite env type definitions
```

---

## Related Documentation

- [GitHub Actions Self-Hosted Runners](https://docs.github.com/en/actions/hosting-your-own-runners)
- [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Docker Compose](https://docs.docker.com/compose/)
- [Traefik PathPrefix Router](https://doc.traefik.io/traefik/routing/routers/)
- [FastAPI Root Path](https://fastapi.tiangolo.com/advanced/behind-a-proxy/)
- [openapi-fetch Documentation](https://openapi-ts.pages.dev/openapi-fetch/)
- [Vite Environment Variables](https://vitejs.dev/guide/env-and-mode.html)
