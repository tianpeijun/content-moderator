#!/usr/bin/env bash
# ============================================================
# build-frontend.sh
# Builds the Vue 3 frontend application for production.
# Output goes to frontend/dist/
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

echo "==> Building frontend..."

cd "$FRONTEND_DIR"

# Install dependencies
echo "==> Installing npm dependencies..."
npm install

# Run production build
echo "==> Running production build..."
npm run build

echo "==> Frontend build complete. Output directory: frontend/dist/"
