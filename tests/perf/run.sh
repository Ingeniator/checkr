#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

MOCK_LLM_PORT=1234
CHECKR_PORT=8080
MOCK_LLM_PID=""
CHECKR_PID=""

cleanup() {
    echo "--- Cleaning up ---"
    [ -n "$CHECKR_PID" ]   && kill "$CHECKR_PID"   2>/dev/null || true
    [ -n "$MOCK_LLM_PID" ] && kill "$MOCK_LLM_PID" 2>/dev/null || true
    wait 2>/dev/null || true
}
trap cleanup EXIT

wait_for_health() {
    local url="$1"
    local name="$2"
    local max_attempts=30
    for i in $(seq 1 $max_attempts); do
        if curl -sf "$url" > /dev/null 2>&1; then
            echo "$name is ready"
            return 0
        fi
        sleep 0.5
    done
    echo "ERROR: $name did not become ready at $url"
    return 1
}

cd "$PROJECT_DIR"

# 1. Start mock LLM server
echo "--- Starting mock LLM server on :$MOCK_LLM_PORT ---"
python3 -m uvicorn tests.perf.mock_llm_server:app \
    --host 0.0.0.0 --port "$MOCK_LLM_PORT" --log-level warning &
MOCK_LLM_PID=$!
wait_for_health "http://localhost:$MOCK_LLM_PORT/health" "Mock LLM"

# 2. Start checkr
echo "--- Starting checkr on :$CHECKR_PORT ---"
CHECKR_PORT=$CHECKR_PORT CHECKR_ROOT_PATH="" GEVAL_API_KEY=mock-key \
    python3 -m uvicorn entrypoint:app \
    --host 0.0.0.0 --port "$CHECKR_PORT" --log-level warning &
CHECKR_PID=$!
wait_for_health "http://localhost:$CHECKR_PORT/health" "Checkr"

# 3. Run Artillery
echo "--- Running Artillery load test ---"
npx artillery run "$SCRIPT_DIR/artillery.yml"
EXIT_CODE=$?

echo "--- Artillery finished with exit code $EXIT_CODE ---"
exit $EXIT_CODE
