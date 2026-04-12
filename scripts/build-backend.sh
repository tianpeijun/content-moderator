#!/usr/bin/env bash
# ============================================================
# build-backend.sh
# Packages the backend Python application for Lambda deployment.
# Creates a deployment artifact directory that CDK's
# Code.fromAsset("../backend") can reference.
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"

echo "==> Building backend Lambda package..."

cd "$BACKEND_DIR"

# Clean previous build artifacts
rm -rf package/
mkdir -p package/

# Install Python dependencies into the package directory (targeting Lambda's Linux x86_64)
echo "==> Installing Python dependencies..."
pip install -r requirements.txt -t package/ --quiet --upgrade --platform manylinux2014_x86_64 --only-binary=:all:

# Copy application source code into the package
echo "==> Copying application source code..."
cp -r app/ package/app/

# Fix import paths: Lambda runs from package/ root, so 'backend.app' → 'app'
echo "==> Fixing import paths for Lambda..."
find package/app/ -name '*.py' -exec sed -i '' 's/from backend\.app\./from app./g' {} +
find package/app/ -name '*.py' -exec sed -i '' 's/import backend\.app\./import app./g' {} +

# Copy alembic config if present (useful for DB migrations)
if [ -f alembic.ini ]; then
  cp alembic.ini package/
fi
if [ -d alembic ]; then
  cp -r alembic/ package/alembic/
fi

echo "==> Backend build complete. Artifact directory: backend/package/"
