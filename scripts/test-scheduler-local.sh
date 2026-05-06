#!/usr/bin/env bash
# Fire the same HTTP triggers as Phase 6 GitHub Actions (local / staging testing).
#
# Usage:
#   chmod +x scripts/test-scheduler-local.sh
#   ./scripts/test-scheduler-local.sh --once
#   ./scripts/test-scheduler-local.sh --interval 300 --target both
#
set -euo pipefail

PHASE1_URL="${PHASE1_URL:-http://127.0.0.1:8000}"
PHASE2_URL="${PHASE2_URL:-http://127.0.0.1:8001}"
INTERVAL=300
TARGET="both"
ONCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --phase1) PHASE1_URL="$2"; shift 2 ;;
    --phase2) PHASE2_URL="$2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --target) TARGET="$2"; shift 2 ;;
    --once) ONCE=1; shift ;;
    -h|--help)
      echo "Usage: $0 [--phase1 URL] [--phase2 URL] [--interval SECONDS] [--target reviews|factsheets|both] [--once]"
      exit 0
      ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

post() {
  local base="$1"
  local path="$2"
  local label="$3"
  base="${base%/}"
  echo "[$label] POST ${base}${path}"
  curl -sS -f -X POST "${base}${path}" -H "Accept: application/json" -w "\nHTTP %{http_code}\n"
}

round() {
  case "$TARGET" in
    reviews)
      post "$PHASE1_URL" "/api/reviews/refresh" "Phase1"
      ;;
    factsheets)
      post "$PHASE2_URL" "/api/faqs/factsheets/refresh" "Phase2 factsheets"
      ;;
    both)
      post "$PHASE1_URL" "/api/reviews/refresh" "Phase1"
      post "$PHASE2_URL" "/api/faqs/factsheets/refresh" "Phase2 factsheets"
      ;;
    *)
      echo "Invalid --target (use reviews, factsheets, or both)"; exit 1
      ;;
  esac
}

if [[ "$ONCE" -eq 1 ]]; then
  round
  exit 0
fi

echo "Loop every ${INTERVAL}s. Ctrl+C to stop."
while true; do
  round
  sleep "$INTERVAL"
done
