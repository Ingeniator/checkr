#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

MOCK_LLM_PORT=1234
CHECKR_PORT=8080
MOCK_LLM_PID=""
CHECKR_PID=""

# Support uv installed either as standalone binary or as Python package.
# Override with UV_RUN env var if needed (e.g. UV_RUN="python3 -m uv run").
if [ -z "${UV_RUN:-}" ]; then
    if command -v uv &>/dev/null; then
        UV_RUN="uv run"
    else
        UV_RUN="python3 -m uv run"
    fi
fi

cleanup() {
    echo "--- Cleaning up ---"
    [ -n "$CHECKR_PID" ]   && kill "$CHECKR_PID"   2>/dev/null || true
    [ -n "$MOCK_LLM_PID" ] && kill "$MOCK_LLM_PID" 2>/dev/null || true
    rm -f "$SCRIPT_DIR"/scenarios/*_generated.yml
    wait 2>/dev/null || true
}
trap cleanup EXIT

kill_port() {
    local port="$1"
    local pids
    pids=$(lsof -ti:"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "Killing stale process(es) on :$port"
        echo "$pids" | xargs kill 2>/dev/null || true
        sleep 0.5
    fi
}

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

# Clean up any stale processes on our ports
kill_port "$MOCK_LLM_PORT"
kill_port "$CHECKR_PORT"

# 1. Start mock LLM server
echo "--- Starting mock LLM server on :$MOCK_LLM_PORT ---"
$UV_RUN uvicorn tests.perf.mock_llm_server:app \
    --host 0.0.0.0 --port "$MOCK_LLM_PORT" --log-level warning &
MOCK_LLM_PID=$!
wait_for_health "http://localhost:$MOCK_LLM_PORT/health" "Mock LLM"

# 2. Start checkr
echo "--- Starting checkr on :$CHECKR_PORT ---"
CHECKR_PORT=$CHECKR_PORT CHECKR_ROOT_PATH="" GEVAL_API_KEY=mock-key \
    $UV_RUN uvicorn entrypoint:app \
    --host 0.0.0.0 --port "$CHECKR_PORT" --log-level warning &
CHECKR_PID=$!
wait_for_health "http://localhost:$CHECKR_PORT/health" "Checkr"

# 3. Generate large-payload scenario (if enabled)
echo "--- Generating large-payload scenario ---"
$UV_RUN python "$SCRIPT_DIR/gen_large_payload.py"

# 4. Assemble Artillery configs (one per unique arrivalRate)
echo "--- Assembling Artillery configs ---"
CONFIGS=$($UV_RUN python "$SCRIPT_DIR/assemble.py")

# 5. Run each config sequentially
echo "--- Running Artillery load tests ---"
OVERALL_EXIT=0
for cfg in $CONFIGS; do
    tag=$(basename "$cfg" .yml | sed 's/artillery_//')
    echo "--- Running $tag ---"
    npx artillery run "$cfg" --output "$SCRIPT_DIR/latest_${tag}.json"
    code=$?
    echo "--- $tag finished with exit code $code ---"
    if [ $code -ne 0 ]; then OVERALL_EXIT=$code; fi
done

if [ $OVERALL_EXIT -ne 0 ]; then
    exit $OVERALL_EXIT
fi

# 6. Compare against baselines
$UV_RUN python "$SCRIPT_DIR/compare.py"
exit $?
