#!/bin/bash
# Web deploy — REACT_APP_API_URL is baked at build time via fly.web.toml [build.args].
# REACT_APP_ADMIN_PASSWORD removed: replaced by the JWT cookie auth layer
# (see Docs/Auth_User_Management_Spec_v1.0.md).
fly deploy --config fly.web.toml --app signal-matrix-web
