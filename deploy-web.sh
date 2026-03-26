#!/bin/bash
source .env
fly deploy --config fly.web.toml --app signal-matrix-web \
  --build-arg REACT_APP_ADMIN_PASSWORD=$REACT_APP_ADMIN_PASSWORD
