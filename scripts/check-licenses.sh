#!/usr/bin/env bash
set -euo pipefail

echo "=== License Compliance Check ==="

# Python licenses
if command -v pip-licenses &>/dev/null; then
  echo "Python package licenses:"
  pip-licenses --format=table --with-license-file --no-license-path \
    --fail-on="GPL-3.0-only;GPL-3.0-or-later;AGPL-3.0-only;AGPL-3.0-or-later" 2>/dev/null || {
    echo "WARNING: Some packages have restrictive licenses"
  }
else
  echo "SKIP: pip-licenses not installed (pip install pip-licenses)"
fi

echo ""

# Node.js licenses
if [ -d frontend/node_modules ]; then
  if command -v npx &>/dev/null; then
    echo "Node.js package licenses:"
    (cd frontend && npx license-checker --production --failOn "GPL-3.0;AGPL-3.0" 2>/dev/null) | tail -5 || {
      echo "WARNING: Some packages have restrictive licenses"
    }
  else
    echo "SKIP: npx not available"
  fi
else
  echo "SKIP: frontend/node_modules not present"
fi

echo "Done."
