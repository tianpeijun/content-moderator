#!/usr/bin/env bash
# ============================================================
# e2e-check.sh
# End-to-end pre-deployment verification script.
#
# Validates all components of the Content Moderation System:
#   1. Backend: pytest (unit + integration tests)
#   2. Frontend: TypeScript type-check + Vite production build
#   3. Infrastructure: CDK TypeScript type-check + cdk synth
#
# Exit code 0 = all checks passed, non-zero = at least one failed.
#
# Usage:
#   ./scripts/e2e-check.sh
# ============================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PASS=0
FAIL=0
RESULTS=()

# Helper: run a check and record result
run_check() {
  local name="$1"
  shift
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  ▶ $name"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  if "$@"; then
    RESULTS+=("✅ PASS  $name")
    PASS=$((PASS + 1))
  else
    RESULTS+=("❌ FAIL  $name")
    FAIL=$((FAIL + 1))
  fi
}

# ── 1. Backend Tests ─────────────────────────────────────────
run_check "Backend: pytest" \
  bash -c "cd '$PROJECT_ROOT/backend' && python -m pytest tests/ -v --tb=short 2>&1"

# ── 2. Frontend Type Check ───────────────────────────────────
run_check "Frontend: vue-tsc type check" \
  bash -c "cd '$PROJECT_ROOT/frontend' && npx vue-tsc --noEmit 2>&1"

# ── 3. Frontend Production Build ─────────────────────────────
run_check "Frontend: vite build" \
  bash -c "cd '$PROJECT_ROOT/frontend' && npx vite build 2>&1"

# ── 4. Infra Type Check ─────────────────────────────────────
run_check "Infra: TypeScript type check" \
  bash -c "cd '$PROJECT_ROOT/infra' && npx tsc --noEmit 2>&1"

# ── 5. Infra CDK Synth ──────────────────────────────────────
run_check "Infra: CDK synth" \
  bash -c "cd '$PROJECT_ROOT/infra' && npx cdk synth --quiet 2>&1"

# ── Summary ──────────────────────────────────────────────────
echo ""
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║        E2E Verification Summary              ║"
echo "╠══════════════════════════════════════════════╣"
for r in "${RESULTS[@]}"; do
  printf "║  %-42s ║\n" "$r"
done
echo "╠══════════════════════════════════════════════╣"
printf "║  Total: %d passed, %d failed                 ║\n" "$PASS" "$FAIL"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── Component Connectivity Map ───────────────────────────────
echo "┌──────────────────────────────────────────────┐"
echo "│  Component Connectivity (Architecture)       │"
echo "├──────────────────────────────────────────────┤"
echo "│                                              │"
echo "│  Business System ──API Key──▶ API Gateway    │"
echo "│                                │             │"
echo "│                    ┌───────────┴──────────┐  │"
echo "│                    ▼                      ▼  │"
echo "│            Moderation API          Admin API │"
echo "│              │      │               │    │   │"
echo "│              ▼      ▼               ▼    ▼   │"
echo "│            RDS   Bedrock          RDS   SQS  │"
echo "│                                         │    │"
echo "│                                         ▼    │"
echo "│                                  Batch Worker│"
echo "│                                    │     │   │"
echo "│                                    ▼     ▼   │"
echo "│                                  RDS  Bedrock│"
echo "│                                              │"
echo "│  Admin Browser ──Cognito──▶ CloudFront ──▶ S3│"
echo "│                                              │"
echo "└──────────────────────────────────────────────┘"
echo ""

if [ "$FAIL" -gt 0 ]; then
  echo "⚠️  Some checks failed. Review the output above before deploying."
  exit 1
fi

echo "🎉 All checks passed! System is ready for deployment."
exit 0
