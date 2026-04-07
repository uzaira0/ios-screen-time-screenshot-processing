#!/bin/bash
# =============================================================================
# Production Deployment Script
# =============================================================================
# This script is called by GitHub Actions to deploy the application.
# It can also be run manually on the server.
#
# Prerequisites:
#   - Docker and Docker Compose installed
#   - .env file configured in /opt/ios-screen-time-screenshot-processing/docker/
#   - Application directory at /opt/ios-screen-time-screenshot-processing/
#
# Environment Variables:
#   IMAGE_TAG - Docker image tag to deploy (default: latest)
#
# Usage:
#   ./scripts/deploy.sh
#   IMAGE_TAG=abc123 ./scripts/deploy.sh
# =============================================================================

set -euo pipefail

# Configuration
APP_DIR="${APP_DIR:-/opt/ios-screen-time-screenshot-processing}"
COMPOSE_FILE="${APP_DIR}/docker/docker-compose.yml"
LOG_FILE="${APP_DIR}/logs/deploy.log"
IMAGE_TAG="${IMAGE_TAG:-latest}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# =============================================================================
# Helper Functions
# =============================================================================

log() {
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${timestamp} $1" | tee -a "$LOG_FILE"
}

log_success() {
    log "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    log "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    log "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log "Checking prerequisites..."

    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi

    # Check Docker Compose
    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi

    # Check compose file exists
    if [ ! -f "$COMPOSE_FILE" ]; then
        log_error "Compose file not found: $COMPOSE_FILE"
        exit 1
    fi

    # Check .env file exists
    if [ ! -f "${APP_DIR}/docker/.env" ]; then
        log_error "Environment file not found: ${APP_DIR}/docker/.env"
        log_error "Copy .env.production.example to .env and configure it"
        exit 1
    fi

    log_success "Prerequisites check passed"
}

pull_images() {
    log "Pulling images with tag: ${IMAGE_TAG}..."

    cd "${APP_DIR}/docker"

    # Update image tags in compose file or use environment variables
    export BACKEND_IMAGE="ghcr.io/${GITHUB_REPOSITORY:-local}/ios-screen-time-screenshot-processing-backend:${IMAGE_TAG}"
    export FRONTEND_IMAGE="ghcr.io/${GITHUB_REPOSITORY:-local}/ios-screen-time-screenshot-processing-frontend:${IMAGE_TAG}"

    docker compose -f docker-compose.yml pull || {
        log_warning "Pull failed, images may need to be built locally"
    }

    log_success "Images pulled successfully"
}

run_migrations() {
    log "Running database migrations..."

    cd "${APP_DIR}/docker"

    # Wait for database to be ready
    for i in {1..30}; do
        if docker compose -f docker-compose.yml exec -T postgres pg_isready -U screenshot &> /dev/null; then
            break
        fi
        log "Waiting for database... (attempt $i/30)"
        sleep 2
    done

    # Run Alembic migrations
    docker compose -f docker-compose.yml exec -T backend alembic upgrade head || {
        log_error "Migration failed"
        exit 1
    }

    log_success "Migrations completed"
}

restart_services() {
    log "Restarting services..."

    cd "${APP_DIR}/docker"

    # Rolling restart to minimize downtime
    # Restart backend first (handles API requests)
    log "Restarting backend..."
    docker compose -f docker-compose.yml up -d --no-deps --force-recreate backend
    sleep 5

    # Restart Celery worker
    log "Restarting Celery worker..."
    docker compose -f docker-compose.yml up -d --no-deps --force-recreate celery-worker
    sleep 3

    # Restart frontend (Nginx)
    log "Restarting frontend..."
    docker compose -f docker-compose.yml up -d --no-deps --force-recreate frontend
    sleep 3

    log_success "Services restarted"
}

health_check() {
    log "Running health checks..."

    local max_attempts=10
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        # Check backend health endpoint (via Traefik)
        if curl -sf http://localhost/screenshot/api/v1/health > /dev/null 2>&1; then
            log_success "Backend health check passed"

            # Check frontend (via Traefik)
            if curl -sf http://localhost/screenshot/ > /dev/null 2>&1; then
                log_success "Frontend health check passed"
                return 0
            fi
        fi

        log "Health check attempt $attempt/$max_attempts failed, retrying..."
        sleep 5
        ((attempt++))
    done

    log_error "Health checks failed after $max_attempts attempts"
    return 1
}

cleanup() {
    log "Cleaning up old images..."

    # Remove dangling images
    docker image prune -f --filter "until=168h" 2>/dev/null || true

    # Remove unused volumes (be careful - only dangling)
    # docker volume prune -f 2>/dev/null || true

    log_success "Cleanup completed"
}

show_status() {
    log "Current container status:"
    cd "${APP_DIR}/docker"
    docker compose -f docker-compose.yml ps
}

# =============================================================================
# Main Execution
# =============================================================================

main() {
    log "=========================================="
    log "Starting deployment"
    log "Image tag: ${IMAGE_TAG}"
    log "App directory: ${APP_DIR}"
    log "=========================================="

    # Create logs directory if it doesn't exist
    mkdir -p "${APP_DIR}/logs"

    # Run deployment steps
    check_prerequisites
    pull_images
    restart_services
    run_migrations
    health_check
    cleanup
    show_status

    log "=========================================="
    log_success "Deployment completed successfully!"
    log "=========================================="
}

# Run main function
main "$@"
