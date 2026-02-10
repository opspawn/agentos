#!/usr/bin/env bash
# HireWire Interactive Demo
# Starts the API server, seeds data, runs demo scenarios, and shows results.
#
# Usage:
#   ./scripts/demo.sh           # Full interactive demo
#   ./scripts/demo.sh --quick   # Quick demo (skip server startup wait)

set -euo pipefail

# ── Colors ──────────────────────────────────────────────────────────────────

BOLD='\033[1m'
DIM='\033[2m'
CYAN='\033[36m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
RESET='\033[0m'

# ── Paths ───────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PORT=${HIREWIRE_PORT:-8000}
BASE_URL="http://localhost:${PORT}"
SERVER_PID=""

# ── Helpers ─────────────────────────────────────────────────────────────────

info()  { echo -e "${CYAN}${BOLD}▸${RESET} $1"; }
ok()    { echo -e "${GREEN}${BOLD}✓${RESET} $1"; }
warn()  { echo -e "${YELLOW}${BOLD}!${RESET} $1"; }
fail()  { echo -e "${RED}${BOLD}✗${RESET} $1"; }
step()  { echo -e "\n${BOLD}━━━ $1 ━━━${RESET}\n"; }

cleanup() {
    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        info "Stopping API server (PID $SERVER_PID)..."
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
        ok "Server stopped."
    fi
}
trap cleanup EXIT

# ── Banner ──────────────────────────────────────────────────────────────────

banner() {
    echo -e "${BOLD}${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                                                            ║"
    echo "║   ██╗  ██╗██╗██████╗ ███████╗██╗    ██╗██╗██████╗ ███████╗║"
    echo "║   ██║  ██║██║██╔══██╗██╔════╝██║    ██║██║██╔══██╗██╔════╝║"
    echo "║   ███████║██║██████╔╝█████╗  ██║ █╗ ██║██║██████╔╝█████╗  ║"
    echo "║   ██╔══██║██║██╔══██╗██╔══╝  ██║███╗██║██║██╔══██╗██╔══╝  ║"
    echo "║   ██║  ██║██║██║  ██║███████╗╚███╔███╔╝██║██║  ██║███████╗║"
    echo "║   ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝╚══════╝ ╚══╝╚══╝ ╚═╝╚═╝  ╚═╝╚══════╝║"
    echo "║                                                            ║"
    echo "║       Interactive Demo — Agent-to-Agent Commerce           ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${RESET}"
    echo -e "${DIM}  Where AI agents discover, hire, and pay each other.${RESET}"
    echo ""
}

# ── Main ────────────────────────────────────────────────────────────────────

main() {
    banner

    QUICK=false
    if [ "${1:-}" = "--quick" ]; then
        QUICK=true
    fi

    # ── Step 1: Check dependencies ──────────────────────────────────────
    step "Step 1: Checking dependencies"

    if ! command -v python3 &>/dev/null; then
        fail "python3 not found. Install Python 3.12+."
        exit 1
    fi
    ok "Python $(python3 --version 2>&1 | awk '{print $2}')"

    if ! python3 -c "import fastapi" 2>/dev/null; then
        warn "FastAPI not installed. Installing dependencies..."
        pip install -r "$PROJECT_DIR/requirements.txt" -q
    fi
    ok "Dependencies installed"

    # ── Step 2: Start API server ────────────────────────────────────────
    step "Step 2: Starting API server"

    # Check if server is already running
    if curl -s "${BASE_URL}/health" >/dev/null 2>&1; then
        ok "API server already running at ${BASE_URL}"
    else
        info "Starting API server on port ${PORT}..."
        cd "$PROJECT_DIR"
        HIREWIRE_DEMO=1 python3 -m uvicorn src.api.main:app --port "$PORT" --host 0.0.0.0 --log-level warning &
        SERVER_PID=$!

        # Wait for server to be ready
        info "Waiting for server to start..."
        for i in $(seq 1 30); do
            if curl -s "${BASE_URL}/health" >/dev/null 2>&1; then
                break
            fi
            sleep 1
            if [ "$i" -eq 30 ]; then
                fail "Server failed to start after 30s"
                exit 1
            fi
        done
        ok "API server running at ${BASE_URL} (PID ${SERVER_PID})"
    fi

    # ── Step 3: Seed demo data ──────────────────────────────────────────
    step "Step 3: Seeding demo data"

    SEED_RESULT=$(curl -s "${BASE_URL}/demo/seed")
    ok "Demo data seeded"
    echo -e "${DIM}$(echo "$SEED_RESULT" | python3 -m json.tool 2>/dev/null || echo "$SEED_RESULT")${RESET}"

    # ── Step 4: Show available agents ───────────────────────────────────
    step "Step 4: Agent Registry"

    info "Querying available agents..."
    AGENTS=$(curl -s "${BASE_URL}/agents")
    AGENT_COUNT=$(echo "$AGENTS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "?")
    ok "${AGENT_COUNT} agents registered"
    echo ""
    echo "$AGENTS" | python3 -c "
import sys, json
agents = json.load(sys.stdin)
for a in agents:
    ext = '(external)' if a.get('is_external') else '(internal)'
    price = a.get('price_per_call', 'free')
    skills = ', '.join(a.get('skills', [])[:3])
    print(f'  {a[\"name\"]:20s} {ext:12s} \${price:>6s}  [{skills}]')
" 2>/dev/null || echo -e "${DIM}$AGENTS${RESET}"

    # ── Step 5: Submit a task ───────────────────────────────────────────
    step "Step 5: Submitting a task to CEO Agent"

    info "Task: \"Build a landing page for an AI startup and deploy it\""
    TASK_RESULT=$(curl -s -X POST "${BASE_URL}/tasks" \
        -H "Content-Type: application/json" \
        -d '{"description": "Build a landing page for an AI startup with modern design, responsive layout, and deploy it", "budget": 10.0}')

    TASK_ID=$(echo "$TASK_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])" 2>/dev/null || echo "unknown")
    ok "Task submitted: ${TASK_ID}"
    echo -e "${DIM}$(echo "$TASK_RESULT" | python3 -m json.tool 2>/dev/null || echo "$TASK_RESULT")${RESET}"

    # Wait for task completion
    info "Waiting for CEO Agent to analyze and delegate..."
    sleep 3

    TASK_STATUS=$(curl -s "${BASE_URL}/tasks/${TASK_ID}")
    STATUS=$(echo "$TASK_STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "unknown")
    if [ "$STATUS" = "completed" ]; then
        ok "Task completed!"
    else
        warn "Task status: ${STATUS} (may still be processing)"
    fi
    echo -e "${DIM}$(echo "$TASK_STATUS" | python3 -m json.tool 2>/dev/null || echo "$TASK_STATUS")${RESET}"

    # ── Step 6: Run marketplace demo ────────────────────────────────────
    step "Step 6: Agent Marketplace Demo"

    info "Running pre-configured marketplace demo..."
    DEMO_RESULT=$(curl -s "${BASE_URL}/demo")
    ok "Marketplace demo complete"
    echo -e "${DIM}$(echo "$DEMO_RESULT" | python3 -m json.tool 2>/dev/null || echo "$DEMO_RESULT")${RESET}"

    # ── Step 7: Check payments ──────────────────────────────────────────
    step "Step 7: Payment Ledger"

    TRANSACTIONS=$(curl -s "${BASE_URL}/transactions")
    TX_COUNT=$(echo "$TRANSACTIONS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
    ok "${TX_COUNT} transactions recorded"
    echo ""
    echo "$TRANSACTIONS" | python3 -c "
import sys, json
txs = json.load(sys.stdin)
for tx in txs[:5]:
    print(f'  {tx[\"from_agent\"]:10s} → {tx[\"to_agent\"]:18s} \${tx[\"amount_usdc\"]:.4f} USDC  [{tx[\"status\"]}]')
if len(txs) > 5:
    print(f'  ... and {len(txs) - 5} more')
" 2>/dev/null || echo -e "${DIM}$TRANSACTIONS${RESET}"

    # ── Step 8: Show metrics ────────────────────────────────────────────
    step "Step 8: System Metrics"

    HEALTH=$(curl -s "${BASE_URL}/health")
    ok "System health"
    echo -e "${DIM}$(echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH")${RESET}"

    echo ""
    COSTS=$(curl -s "${BASE_URL}/metrics/costs")
    ok "Cost analytics"
    echo -e "${DIM}$(echo "$COSTS" | python3 -m json.tool 2>/dev/null || echo "$COSTS")${RESET}"

    # ── Step 9: Run Python demo scenarios ───────────────────────────────
    step "Step 9: Running Python Demo Scenarios"

    info "Running all demo scenarios (landing-page, research, agent-hiring)..."
    cd "$PROJECT_DIR"
    python3 demo/run_demo.py all 2>&1 || warn "Some demo scenarios may have warnings (expected with mock provider)"

    # ── Summary ─────────────────────────────────────────────────────────
    step "Demo Complete"

    echo -e "${GREEN}${BOLD}"
    echo "  HireWire is running and ready."
    echo ""
    echo "  Dashboard:     ${BASE_URL}"
    echo "  API Docs:      ${BASE_URL}/docs"
    echo "  Health:        ${BASE_URL}/health"
    echo "  Agents:        ${BASE_URL}/agents"
    echo "  Transactions:  ${BASE_URL}/transactions"
    echo "  Metrics:       ${BASE_URL}/metrics/costs"
    echo -e "${RESET}"

    if [ -n "$SERVER_PID" ]; then
        echo -e "${DIM}Server running in background (PID ${SERVER_PID}). Press Ctrl+C to stop.${RESET}"
        echo ""

        # Keep running until user exits
        if [ "$QUICK" = false ]; then
            wait "$SERVER_PID" 2>/dev/null || true
        fi
    fi
}

main "$@"
