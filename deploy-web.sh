#!/bin/bash
# Read password directly from .env — avoids BOM and ! history-expansion issues
REACT_APP_ADMIN_PASSWORD=$(grep -m1 'REACT_APP_ADMIN_PASSWORD=' .env | cut -d'=' -f2-)

fly deploy --config fly.web.toml --app signal-matrix-web \
  --build-arg "REACT_APP_ADMIN_PASSWORD=${REACT_APP_ADMIN_PASSWORD}"
