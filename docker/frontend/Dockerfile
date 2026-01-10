# =============================================================================
# Frontend Dockerfile - ios-screen-time-screenshot-processing
# =============================================================================
# Multi-stage build: Bun for building, Nginx for serving
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Build
# -----------------------------------------------------------------------------
FROM oven/bun:1-alpine AS build

# Install Python and build dependencies for native modules (better-sqlite3)
# Cache bust: 2026-01-10 - axios removal
RUN apk add --no-cache python3 make g++ && echo "cache-bust-2026-01-10-axios-removed"

WORKDIR /app

# Build argument for API path (set by docker-compose)
ARG APP_PATH_PREFIX=/screenshot
ENV VITE_API_BASE_URL=${APP_PATH_PREFIX}/api/v1
ENV VITE_BASE_PATH=${APP_PATH_PREFIX}

# Copy package files (paths relative to monorepo root context)
COPY apps/ios-screen-time-screenshot-processing/frontend/package.json apps/ios-screen-time-screenshot-processing/frontend/bun.lock* apps/ios-screen-time-screenshot-processing/frontend/package-lock.json* ./

# Install dependencies
RUN bun install

# Copy source
COPY apps/ios-screen-time-screenshot-processing/frontend/ ./

# Build for production
RUN bun run build

# -----------------------------------------------------------------------------
# Stage 2: Serve with Nginx
# -----------------------------------------------------------------------------
FROM nginx:alpine AS production

# Install curl for healthcheck (wget has issues with localhost in Alpine)
RUN apk add --no-cache curl

# Copy built assets
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx config (path relative to monorepo root context)
COPY apps/ios-screen-time-screenshot-processing/docker/nginx/nginx.conf /etc/nginx/nginx.conf

# Copy entrypoint script for BASE_PATH injection
COPY apps/ios-screen-time-screenshot-processing/docker/frontend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Run nginx as non-root (nginx user already exists in nginx:alpine)
RUN chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /var/log/nginx && \
    touch /var/run/nginx.pid && chown nginx:nginx /var/run/nginx.pid

EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
