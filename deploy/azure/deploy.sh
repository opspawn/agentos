#!/usr/bin/env bash
# -------------------------------------------------------------------
# HireWire — Azure Container Apps deployment (Bicep-based)
#
# Usage:
#   ./deploy/azure/deploy.sh                    # Full deploy (infra + build + push + app)
#   ./deploy/azure/deploy.sh infra              # Deploy Azure infrastructure only
#   ./deploy/azure/deploy.sh build              # Build Docker image only
#   ./deploy/azure/deploy.sh push               # Push image to ACR only
#   ./deploy/azure/deploy.sh app                # Update container app only
#   ./deploy/azure/deploy.sh smoke              # Run smoke tests against deployed app
#
# Environment:
#   AZURE_RESOURCE_GROUP  — Target resource group (required)
#   APP_NAME              — Container app name (default: hirewire-api)
#   AZURE_OPENAI_ENDPOINT — Azure OpenAI endpoint (optional for infra)
#   AZURE_OPENAI_KEY      — Azure OpenAI key (optional for infra)
# -------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load .env if present
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_DIR/.env"
    set +a
fi

# Configuration
: "${AZURE_RESOURCE_GROUP:?AZURE_RESOURCE_GROUP not set. Export it or add to .env}"
APP_NAME="${APP_NAME:-hirewire-api}"
IMAGE_NAME="hirewire-api"
IMAGE_TAG="${IMAGE_TAG:-latest}"
BICEP_FILE="$SCRIPT_DIR/main.bicep"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${BLUE}==>${NC} $1"; }
success() { echo -e "${GREEN}==>${NC} $1"; }
warn() { echo -e "${YELLOW}==>${NC} $1"; }

# -------------------------------------------------------------------
# Commands
# -------------------------------------------------------------------

deploy_infra() {
    log "Deploying Azure infrastructure via Bicep..."

    az deployment group create \
        --resource-group "$AZURE_RESOURCE_GROUP" \
        --template-file "$BICEP_FILE" \
        --parameters \
            appName="$APP_NAME" \
            azureOpenAIEndpoint="${AZURE_OPENAI_ENDPOINT:-}" \
            azureOpenAIKey="${AZURE_OPENAI_KEY:-}" \
            azureOpenAIDeployment="${AZURE_OPENAI_DEPLOYMENT:-gpt-4o}" \
        --query "properties.outputs" \
        --output table

    success "Infrastructure deployed"
}

get_acr_server() {
    az deployment group show \
        --resource-group "$AZURE_RESOURCE_GROUP" \
        --name main \
        --query "properties.outputs.acrLoginServer.value" \
        --output tsv 2>/dev/null || echo "${APP_NAME//-/}acr.azurecr.io"
}

build_image() {
    log "Building Docker image: ${IMAGE_NAME}:${IMAGE_TAG}"
    docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" "$PROJECT_DIR"
    success "Image built: ${IMAGE_NAME}:${IMAGE_TAG}"
}

push_image() {
    local ACR_SERVER
    ACR_SERVER=$(get_acr_server)
    local FULL_IMAGE="${ACR_SERVER}/${IMAGE_NAME}:${IMAGE_TAG}"

    log "Logging in to ACR: ${ACR_SERVER}"
    az acr login --name "${ACR_SERVER%%.*}"

    log "Tagging and pushing: ${FULL_IMAGE}"
    docker tag "${IMAGE_NAME}:${IMAGE_TAG}" "$FULL_IMAGE"
    docker push "$FULL_IMAGE"
    success "Image pushed: ${FULL_IMAGE}"
}

update_app() {
    local ACR_SERVER
    ACR_SERVER=$(get_acr_server)
    local FULL_IMAGE="${ACR_SERVER}/${IMAGE_NAME}:${IMAGE_TAG}"

    log "Updating container app: ${APP_NAME}"
    az containerapp update \
        --name "$APP_NAME" \
        --resource-group "$AZURE_RESOURCE_GROUP" \
        --image "$FULL_IMAGE"

    local FQDN
    FQDN=$(az containerapp show \
        --name "$APP_NAME" \
        --resource-group "$AZURE_RESOURCE_GROUP" \
        --query "properties.configuration.ingress.fqdn" \
        --output tsv)

    echo ""
    success "========================================="
    success "  HireWire deployed successfully!"
    success "  URL:       https://${FQDN}"
    success "  Health:    https://${FQDN}/health"
    success "  Azure:     https://${FQDN}/health/azure"
    success "  Dashboard: https://${FQDN}/"
    success "  API Docs:  https://${FQDN}/docs"
    success "========================================="
}

smoke_test() {
    local FQDN
    FQDN=$(az containerapp show \
        --name "$APP_NAME" \
        --resource-group "$AZURE_RESOURCE_GROUP" \
        --query "properties.configuration.ingress.fqdn" \
        --output tsv 2>/dev/null)

    if [ -z "$FQDN" ]; then
        warn "Container app not found. Deploy first."
        exit 1
    fi

    local BASE="https://${FQDN}"
    local PASS=0 FAIL=0

    check() {
        local name=$1 url=$2 expect=$3
        local status
        status=$(curl -s -o /dev/null -w "%{http_code}" "$url" --max-time 10 2>/dev/null || echo "000")
        if [ "$status" = "$expect" ]; then
            success "  PASS: $name ($status)"
            PASS=$((PASS + 1))
        else
            warn "  FAIL: $name (got $status, expected $expect)"
            FAIL=$((FAIL + 1))
        fi
    }

    log "Running smoke tests against ${BASE}..."
    check "Health endpoint" "$BASE/health" "200"
    check "Dashboard" "$BASE/" "200"
    check "Agents list" "$BASE/agents" "200"
    check "Tasks list" "$BASE/tasks" "200"
    check "Transactions" "$BASE/transactions" "200"
    check "Activity feed" "$BASE/activity" "200"
    check "Metrics" "$BASE/metrics" "200"
    check "HITL stats" "$BASE/approvals/stats" "200"
    check "RAI status" "$BASE/responsible-ai/status" "200"
    check "A2A agent card" "$BASE/.well-known/agent.json" "200"
    check "MCP tools" "$BASE/mcp/tools" "200"
    check "API docs" "$BASE/docs" "200"

    echo ""
    success "Results: ${PASS} passed, ${FAIL} failed out of $((PASS + FAIL)) tests"
    [ "$FAIL" -eq 0 ] && exit 0 || exit 1
}

# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

case "${1:-all}" in
    infra)  deploy_infra ;;
    build)  build_image ;;
    push)   push_image ;;
    app)    update_app ;;
    smoke)  smoke_test ;;
    all)    deploy_infra && build_image && push_image && update_app && smoke_test ;;
    *)
        echo "Usage: $0 {infra|build|push|app|smoke|all}"
        exit 1
        ;;
esac
