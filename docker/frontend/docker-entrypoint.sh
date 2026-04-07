#!/bin/sh
# Generate runtime config from environment variables
# API_BASE_URL determines server vs WASM mode:
#   - Set API_BASE_URL (e.g. "/ios-screen-time-screenshot-processing/api/v1") → server mode
#   - Omit API_BASE_URL → WASM mode (offline, client-side only)
if [ -n "$API_BASE_URL" ]; then
  cat > /usr/share/nginx/html/config.js << JSEOF
window.__CONFIG__ = {
  basePath: "${BASE_PATH:-}",
  apiBaseUrl: "${API_BASE_URL}",
};
JSEOF
else
  cat > /usr/share/nginx/html/config.js << JSEOF
window.__CONFIG__ = {
  basePath: "${BASE_PATH:-}",
};
JSEOF
fi

# Inject base href if BASE_PATH is set (idempotent - skip if already present)
if [ -n "$BASE_PATH" ]; then
    if ! grep -q '<base href=' /usr/share/nginx/html/index.html; then
        sed -i "s|<head>|<head><base href=\"${BASE_PATH}/\">|" /usr/share/nginx/html/index.html
    fi
fi

# Start nginx
exec nginx -g "daemon off;"
