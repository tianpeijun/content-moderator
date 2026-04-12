#!/usr/bin/env bash
# ============================================================
# deploy.sh
# Main deployment script for the Content Moderation System.
#
# Steps:
#   1. Build backend Lambda package
#   2. Build frontend production assets
#   3. Deploy infrastructure via CDK
#   4. Upload frontend assets to S3
#   5. Invalidate CloudFront cache
#
# Usage:
#   ./scripts/deploy.sh              # full deploy
#   ./scripts/deploy.sh --skip-build # skip build steps, CDK deploy only
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STACK_NAME="ContentModerationStack"

SKIP_BUILD=false
if [[ "${1:-}" == "--skip-build" ]]; then
  SKIP_BUILD=true
fi

# ── Step 1: Build backend ────────────────────────────────────
if [ "$SKIP_BUILD" = false ]; then
  echo ""
  echo "============================================"
  echo "  Step 1/5: Building backend"
  echo "============================================"
  bash "$SCRIPT_DIR/build-backend.sh"
fi

# ── Step 2: Build frontend ───────────────────────────────────
if [ "$SKIP_BUILD" = false ]; then
  echo ""
  echo "============================================"
  echo "  Step 2/5: Building frontend"
  echo "============================================"
  bash "$SCRIPT_DIR/build-frontend.sh"
fi

# ── Step 3: CDK deploy ───────────────────────────────────────
echo ""
echo "============================================"
echo "  Step 3/5: Deploying infrastructure (CDK)"
echo "============================================"
cd "$PROJECT_ROOT/infra"
npm install
npx cdk deploy "$STACK_NAME" --require-approval never --outputs-file cdk-outputs.json

# ── Step 4: Upload frontend to S3 ────────────────────────────
echo ""
echo "============================================"
echo "  Step 4/5: Uploading frontend to S3"
echo "============================================"

# Extract bucket name and distribution ID from CDK outputs
FRONTEND_BUCKET=$(jq -r ".${STACK_NAME}.FrontendBucketName" "$PROJECT_ROOT/infra/cdk-outputs.json")
DISTRIBUTION_ID=$(jq -r ".${STACK_NAME}.DistributionId" "$PROJECT_ROOT/infra/cdk-outputs.json")

if [ -z "$FRONTEND_BUCKET" ] || [ "$FRONTEND_BUCKET" = "null" ]; then
  echo "ERROR: Could not find FrontendBucketName in CDK outputs."
  echo "Make sure the stack exports FrontendBucketName."
  exit 1
fi

echo "==> Syncing frontend/dist/ to s3://$FRONTEND_BUCKET/"
aws s3 sync "$PROJECT_ROOT/frontend/dist/" "s3://$FRONTEND_BUCKET/" --delete

# ── Step 5: Invalidate CloudFront cache ──────────────────────
echo ""
echo "============================================"
echo "  Step 5/5: Invalidating CloudFront cache"
echo "============================================"

if [ -z "$DISTRIBUTION_ID" ] || [ "$DISTRIBUTION_ID" = "null" ]; then
  echo "WARNING: Could not find DistributionId in CDK outputs. Skipping invalidation."
else
  echo "==> Invalidating CloudFront distribution: $DISTRIBUTION_ID"
  aws cloudfront create-invalidation \
    --distribution-id "$DISTRIBUTION_ID" \
    --paths "/*"
fi

echo ""
echo "============================================"
echo "  Deployment complete!"
echo "============================================"

# Print useful outputs
FRONTEND_URL=$(jq -r ".${STACK_NAME}.FrontendUrl" "$PROJECT_ROOT/infra/cdk-outputs.json" 2>/dev/null || echo "N/A")
API_URL=$(jq -r ".${STACK_NAME}.ApiUrl" "$PROJECT_ROOT/infra/cdk-outputs.json" 2>/dev/null || echo "N/A")

echo "  Frontend URL : $FRONTEND_URL"
echo "  API URL      : $API_URL"
echo ""
