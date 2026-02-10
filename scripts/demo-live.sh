#!/usr/bin/env bash
# HireWire LIVE Demo — Azure OpenAI + Cosmos DB
#
# Sources Azure credentials, starts the API server with real GPT-4o,
# runs the landing page demo scenario, and displays token/cost metrics.
#
# Usage:
#   ./scripts/demo-live.sh                    # Full live demo
#   ./scripts/demo-live.sh --quick            # Quick (no server keep-alive)
#   ./scripts/demo-live.sh --scenario all     # Run all scenarios

set -euo pipefail

# ── Colors ──────────────────────────────────────────────────────────────────

BOLD='\033[1m'
DIM='\033[2m'
CYAN='\033[36m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
MAGENTA='\033[35m'
RESET='\033[0m'

# ── Paths ───────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="${AZURE_ENV_FILE:-/home/agent/credentials/azure-hackathon.env}"
PORT=${HIREWIRE_PORT:-8000}
BASE_URL="http://localhost:${PORT}"
SERVER_PID=""
SCENARIO="${HIREWIRE_SCENARIO:-landing-page}"

# ── Helpers ─────────────────────────────────────────────────────────────────

info()    { echo -e "${CYAN}${BOLD}▸${RESET} $1"; }
ok()      { echo -e "${GREEN}${BOLD}✓${RESET} $1"; }
warn()    { echo -e "${YELLOW}${BOLD}!${RESET} $1"; }
fail()    { echo -e "${RED}${BOLD}✗${RESET} $1"; }
step()    { echo -e "\n${BOLD}${MAGENTA}━━━ $1 ━━━${RESET}\n"; }
metric()  { echo -e "  ${CYAN}$1${RESET}: ${BOLD}$2${RESET}"; }

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
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║                                                                ║"
    echo "║   ██╗  ██╗██╗██████╗ ███████╗██╗    ██╗██╗██████╗ ███████╗    ║"
    echo "║   ██║  ██║██║██╔══██╗██╔════╝██║    ██║██║██╔══██╗██╔════╝    ║"
    echo "║   ███████║██║██████╔╝█████╗  ██║ █╗ ██║██║██████╔╝█████╗      ║"
    echo "║   ██╔══██║██║██╔══██╗██╔══╝  ██║███╗██║██║██╔══██╗██╔══╝      ║"
    echo "║   ██║  ██║██║██║  ██║███████╗╚███╔███╔╝██║██║  ██║███████╗    ║"
    echo "║   ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝╚══════╝ ╚══╝╚══╝ ╚═╝╚═╝  ╚═╝╚══════╝    ║"
    echo "║                                                                ║"
    echo "║       LIVE Demo — Real GPT-4o on Azure OpenAI                  ║"
    echo "║       Agent-to-Agent Commerce with x402 Payments               ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo -e "${RESET}"
    echo -e "${DIM}  Where AI agents discover, hire, and pay each other — powered by Azure.${RESET}"
    echo ""
}

# ── Main ────────────────────────────────────────────────────────────────────

main() {
    banner

    QUICK=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --quick) QUICK=true; shift;;
            --scenario) SCENARIO="$2"; shift 2;;
            *) shift;;
        esac
    done

    # ── Step 1: Source Azure credentials ─────────────────────────────────
    step "Step 1: Loading Azure Credentials"

    if [ ! -f "$ENV_FILE" ]; then
        fail "Azure credentials not found: $ENV_FILE"
        echo -e "${DIM}  Set AZURE_ENV_FILE or ensure credentials/azure-hackathon.env exists${RESET}"
        exit 1
    fi

    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a

    # Let auto-detection pick up Azure vars (don't set MODEL_PROVIDER so
    # _resolve_provider sees the AZURE_OPENAI_* vars and upgrades from mock)
    unset MODEL_PROVIDER 2>/dev/null || true

    ok "Azure OpenAI endpoint: ${AZURE_OPENAI_ENDPOINT:-not set}"
    ok "Azure OpenAI deployment: ${AZURE_OPENAI_DEPLOYMENT:-gpt-4o}"
    ok "Cosmos DB endpoint: ${COSMOS_ENDPOINT:-not configured}"
    echo ""

    # ── Step 2: Verify Azure connectivity ────────────────────────────────
    step "Step 2: Verifying Azure Connectivity"

    info "Testing Azure OpenAI connection..."
    AZURE_TEST=$(cd "$PROJECT_DIR" && python3 -c "
from src.framework.azure_llm import AzureLLMProvider
p = AzureLLMProvider()
r = p.check_connection()
if r['connected']:
    print(f'CONNECTED model={r.get(\"model\", \"unknown\")}')
else:
    print(f'FAILED: {r.get(\"error\", \"unknown\")}')
" 2>&1)

    if [[ "$AZURE_TEST" == CONNECTED* ]]; then
        ok "Azure OpenAI: $AZURE_TEST"
    else
        fail "Azure OpenAI: $AZURE_TEST"
        exit 1
    fi

    if [ -n "${COSMOS_ENDPOINT:-}" ]; then
        info "Testing Cosmos DB connection..."
        COSMOS_TEST=$(cd "$PROJECT_DIR" && python3 -c "
from src.persistence.cosmos import CosmosDBStore
s = CosmosDBStore()
r = s.check_connection()
if r['connected']:
    print(f'CONNECTED databases={r.get(\"databases\", 0)}')
else:
    print(f'FAILED: {r.get(\"error\", \"unknown\")}')
" 2>&1)

        if [[ "$COSMOS_TEST" == CONNECTED* ]]; then
            ok "Cosmos DB: $COSMOS_TEST"
        else
            warn "Cosmos DB: $COSMOS_TEST (continuing without cloud persistence)"
        fi
    fi
    echo ""

    # ── Step 3: Start API server ─────────────────────────────────────────
    step "Step 3: Starting API Server (Azure-backed)"

    if curl -s "${BASE_URL}/health" >/dev/null 2>&1; then
        ok "API server already running at ${BASE_URL}"
    else
        info "Starting HireWire API with Azure OpenAI provider..."
        cd "$PROJECT_DIR"
        HIREWIRE_DEMO=1 python3 -m uvicorn src.api.main:app \
            --port "$PORT" --host 0.0.0.0 --log-level warning &
        SERVER_PID=$!

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
    echo ""

    # ── Step 4: Verify Azure health endpoint ─────────────────────────────
    step "Step 4: Azure Health Check (via API)"

    AZURE_HEALTH=$(curl -s "${BASE_URL}/health/azure")
    echo -e "${DIM}$(echo "$AZURE_HEALTH" | python3 -m json.tool 2>/dev/null || echo "$AZURE_HEALTH")${RESET}"
    echo ""

    # ── Step 5: Seed demo data ───────────────────────────────────────────
    step "Step 5: Seeding Demo Data"

    SEED_RESULT=$(curl -s "${BASE_URL}/demo/seed")
    ok "Demo data seeded"
    echo -e "${DIM}$(echo "$SEED_RESULT" | python3 -m json.tool 2>/dev/null || echo "$SEED_RESULT")${RESET}"
    echo ""

    # ── Step 6: Run live demo scenario ───────────────────────────────────
    step "Step 6: Running Live Demo — Real GPT-4o Responses"

    info "Scenario: ${SCENARIO}"
    info "This uses REAL Azure OpenAI calls — watch for actual AI-generated content!"
    echo ""

    T_START=$(date +%s%N)

    cd "$PROJECT_DIR"
    python3 demo/run_demo.py "$SCENARIO" 2>&1

    T_END=$(date +%s%N)
    ELAPSED_MS=$(( (T_END - T_START) / 1000000 ))
    echo ""
    ok "Demo scenario complete in ${ELAPSED_MS}ms"

    # ── Step 6b: Cosmos DB persistence ──────────────────────────────────
    if [ -n "${COSMOS_ENDPOINT:-}" ]; then
        step "Step 6b: Cosmos DB Cloud Persistence"

        info "Persisting demo results to Azure Cosmos DB..."
        cd "$PROJECT_DIR"
        python3 -c "
import sys, time, uuid
sys.path.insert(0, '.')
from src.persistence.cosmos import get_cosmos_store

store = get_cosmos_store()

# Persist the demo run as a job
job_id = f'demo-live-{uuid.uuid4().hex[:8]}'
store.save_job({
    'id': job_id,
    'description': 'Live demo: Sequential workflow with GPT-4o',
    'status': 'completed',
    'workflow': 'sequential',
    'agents': ['Research', 'CEO', 'Builder'],
    'elapsed_ms': ${ELAPSED_MS},
    'completed_at': time.time(),
})

# Read it back to verify
job = store.get_job(job_id)
print(f'  Job {job_id} persisted to Cosmos DB')
print(f'  Read-back: status={job[\"status\"]}, workflow={job[\"workflow\"]}')
print(f'  \033[32m✓\033[0m Cloud persistence verified')
" 2>&1
        echo ""
    fi

    # ── Step 7: Show payment ledger ──────────────────────────────────────
    step "Step 7: Payment Ledger"

    TRANSACTIONS=$(curl -s "${BASE_URL}/transactions")
    TX_COUNT=$(echo "$TRANSACTIONS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
    ok "${TX_COUNT} transactions recorded"
    echo ""
    echo "$TRANSACTIONS" | python3 -c "
import sys, json
txs = json.load(sys.stdin)
total = sum(tx['amount_usdc'] for tx in txs)
for tx in txs[:10]:
    print(f'  {tx[\"from_agent\"]:10s} → {tx[\"to_agent\"]:18s} \${tx[\"amount_usdc\"]:.4f} USDC  [{tx[\"status\"]}]')
if len(txs) > 10:
    print(f'  ... and {len(txs) - 10} more')
print(f'\n  Total: \${total:.4f} USDC')
" 2>/dev/null || echo -e "${DIM}$TRANSACTIONS${RESET}"

    # ── Step 8: Cost and token metrics ───────────────────────────────────
    step "Step 8: Cost & Token Usage"

    HEALTH=$(curl -s "${BASE_URL}/health")
    COSTS=$(curl -s "${BASE_URL}/metrics/costs")

    echo -e "${BOLD}System Health:${RESET}"
    echo -e "${DIM}$(echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH")${RESET}"
    echo ""
    echo -e "${BOLD}Cost Analytics:${RESET}"
    echo -e "${DIM}$(echo "$COSTS" | python3 -m json.tool 2>/dev/null || echo "$COSTS")${RESET}"
    echo ""

    # Provider summary
    cd "$PROJECT_DIR"
    python3 -c "
from src.config import get_settings, _resolve_provider, ModelProvider
settings = get_settings()
provider = _resolve_provider(settings)
print(f'  Provider   : {provider.value}')
if provider == ModelProvider.AZURE_OPENAI:
    print(f'  Deployment : {settings.azure_openai_deployment}')
    print(f'  Endpoint   : {settings.azure_openai_endpoint}')
print(f'  Cosmos DB  : {\"enabled\" if settings.cosmos_endpoint else \"not configured\"}')
if provider == ModelProvider.AZURE_OPENAI:
    print()
    print('  \033[2mPricing: GPT-4o \$2.50/1M input + \$10.00/1M output tokens\033[0m')
    print('  \033[2mToken counts and costs are shown in the scenario output above.\033[0m')
" 2>/dev/null || true

    # ── Summary ──────────────────────────────────────────────────────────
    step "Demo Complete"

    echo -e "${GREEN}${BOLD}"
    echo "  HireWire is running with REAL Azure OpenAI (GPT-4o)."
    echo ""
    echo "  Dashboard:      ${BASE_URL}"
    echo "  API Docs:       ${BASE_URL}/docs"
    echo "  Azure Health:   ${BASE_URL}/health/azure"
    echo "  Agents:         ${BASE_URL}/agents"
    echo "  Transactions:   ${BASE_URL}/transactions"
    echo "  Cost Metrics:   ${BASE_URL}/metrics/costs"
    echo -e "${RESET}"

    echo -e "${DIM}  Powered by: Azure OpenAI (GPT-4o) + Cosmos DB + x402 Payments${RESET}"
    echo -e "${DIM}  Microsoft AI Dev Days 2026${RESET}"
    echo ""

    if [ -n "$SERVER_PID" ]; then
        echo -e "${DIM}Server running in background (PID ${SERVER_PID}). Press Ctrl+C to stop.${RESET}"
        echo ""

        if [ "$QUICK" = false ]; then
            wait "$SERVER_PID" 2>/dev/null || true
        fi
    fi
}

main "$@"
