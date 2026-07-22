#!/usr/bin/env bash
# =============================================================================
# Backend Dockerfile Smoke Test
# =============================================================================
# This script validates that the Backend Docker image builds and runs correctly.
#
# Checks performed:
#   1. Image builds without errors
#   2. `python -c "import dev_ghost_parser"` runs without import errors
#   3. `git --version` returns valid output
#   4. `GET /docs` returns HTTP 200 within 30 seconds of container start
#
# Requirements validated: 4.1, 4.2, 4.3, 4.6
#
# Usage:
#   cd backend/
#   chmod +x smoke-test.sh
#   ./smoke-test.sh
#
# Prerequisites:
#   - Docker installed and running
#   - Script executed from the backend/ directory
# =============================================================================

set -euo pipefail

IMAGE_NAME="devghost-backend"
CONTAINER_NAME="devghost-backend-smoke-test"
HOST_PORT=8000
MAX_WAIT=30

# Track results
PASS=0
FAIL=0
RESULTS=()

# Utility: record a test result
record() {
  local status="$1"
  local description="$2"
  if [ "$status" = "PASS" ]; then
    PASS=$((PASS + 1))
    RESULTS+=("✅ PASS: $description")
  else
    FAIL=$((FAIL + 1))
    RESULTS+=("❌ FAIL: $description")
  fi
}

# Cleanup function to ensure container is removed on exit
cleanup() {
  echo ""
  echo "🧹 Cleaning up..."
  docker stop "$CONTAINER_NAME" 2>/dev/null || true
  docker rm "$CONTAINER_NAME" 2>/dev/null || true
}

trap cleanup EXIT

echo "=============================================="
echo "  Backend Dockerfile Smoke Test"
echo "=============================================="
echo ""

# --------------------------------------------------------------------------
# Test 1: Image builds without errors
# --------------------------------------------------------------------------
echo "🔨 [1/4] Building Docker image '$IMAGE_NAME'..."
if docker build -t "$IMAGE_NAME" .; then
  record "PASS" "Docker image builds without errors"
else
  record "FAIL" "Docker image build failed"
  echo "❌ Build failed. Cannot proceed with remaining tests."
  # Print summary and exit early
  echo ""
  echo "=============================================="
  echo "  Results Summary"
  echo "=============================================="
  for r in "${RESULTS[@]}"; do echo "  $r"; done
  echo ""
  echo "  Passed: $PASS | Failed: $FAIL | Total: $((PASS + FAIL))"
  echo "=============================================="
  exit 1
fi
echo ""

# --------------------------------------------------------------------------
# Test 2: Python import works
# --------------------------------------------------------------------------
echo "🐍 [2/4] Verifying 'import dev_ghost_parser'..."
if docker run --rm "$IMAGE_NAME" python -c "import dev_ghost_parser"; then
  record "PASS" "python -c 'import dev_ghost_parser' succeeds"
else
  record "FAIL" "python -c 'import dev_ghost_parser' failed"
fi
echo ""

# --------------------------------------------------------------------------
# Test 3: Git is installed
# --------------------------------------------------------------------------
echo "🔧 [3/4] Verifying 'git --version'..."
GIT_OUTPUT=$(docker run --rm "$IMAGE_NAME" git --version 2>&1)
if echo "$GIT_OUTPUT" | grep -q "^git version"; then
  record "PASS" "git --version returns valid output: $GIT_OUTPUT"
else
  record "FAIL" "git --version did not return expected output: $GIT_OUTPUT"
fi
echo ""

# --------------------------------------------------------------------------
# Test 4: GET /docs returns HTTP 200 within 30 seconds
# --------------------------------------------------------------------------
echo "🌐 [4/4] Starting container and verifying GET /docs..."

# Start the container in the background
docker run -d --name "$CONTAINER_NAME" -p "$HOST_PORT:8000" "$IMAGE_NAME"

# Wait for the server to be ready (poll up to MAX_WAIT seconds)
echo "   Waiting up to ${MAX_WAIT}s for server to start..."
ELAPSED=0
SERVER_READY=false

while [ $ELAPSED -lt $MAX_WAIT ]; do
  HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${HOST_PORT}/docs" 2>/dev/null || echo "000")
  if [ "$HTTP_STATUS" = "200" ]; then
    SERVER_READY=true
    break
  fi
  sleep 1
  ELAPSED=$((ELAPSED + 1))
done

if [ "$SERVER_READY" = true ]; then
  record "PASS" "GET /docs returned HTTP 200 after ${ELAPSED}s"
else
  record "FAIL" "GET /docs did not return HTTP 200 within ${MAX_WAIT}s (last status: $HTTP_STATUS)"
fi
echo ""

# ==========================================================================
# Summary
# ==========================================================================
echo "=============================================="
echo "  Results Summary"
echo "=============================================="
for r in "${RESULTS[@]}"; do
  echo "  $r"
done
echo ""
echo "  Passed: $PASS | Failed: $FAIL | Total: $((PASS + FAIL))"
echo "=============================================="

# Exit with non-zero status if any test failed
if [ $FAIL -gt 0 ]; then
  exit 1
fi

echo ""
echo "🎉 All smoke tests passed!"
exit 0
