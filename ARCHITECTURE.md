# HireWire Architecture

Detailed system design for HireWire — a multi-agent operating system with real payments.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                             HireWire Platform                                    │
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────┐    │
│  │                          API Layer (FastAPI)                             │    │
│  │  POST /tasks │ GET /agents │ GET /transactions │ GET /metrics │ /health  │    │
│  └───────┬──────────────────────────────────┬──────────────────────────────┘    │
│          │                                  │                                    │
│  ┌───────▼──────────┐         ┌─────────────▼────────────┐                      │
│  │   CEO Agent       │         │     Dashboard / UI       │                      │
│  │                   │         │  Real-time metrics,       │                      │
│  │  • Task analysis  │         │  cost analysis, demo mode │                      │
│  │  • Hiring decisions│        └──────────────────────────┘                      │
│  │  • Budget control │                                                           │
│  │  • Quality review │                                                           │
│  └───────┬───────────┘                                                           │
│          │                                                                       │
│  ┌───────▼─────────────────────────────────────────────────────────────────┐    │
│  │                      Orchestration Engine                               │    │
│  │                                                                         │    │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌──────────────┐    │    │
│  │  │ Sequential  │ │ Concurrent  │ │ Group Chat  │ │   Handoff    │    │    │
│  │  │   Pipeline  │ │  Parallel   │ │ Multi-agent │ │  Delegation  │    │    │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └──────────────┘    │    │
│  └───────┬──────────────────────────────────┬──────────────────────────────┘    │
│          │                                  │                                    │
│  ┌───────▼──────────┐         ┌─────────────▼────────────┐                      │
│  │  Internal Agents  │         │    Marketplace Layer     │                      │
│  │                   │         │                          │                      │
│  │  • Builder Agent  │         │  ┌──────────────────┐   │                      │
│  │  • Research Agent │         │  │  Agent Registry   │   │                      │
│  │  • Analyst Agent  │         │  │  (MCP Server)     │   │                      │
│  │  • Executor Agent │         │  └──────────────────┘   │                      │
│  └───────────────────┘         │  ┌──────────────────┐   │                      │
│                                │  │  Hiring Manager   │   │                      │
│                                │  │  (7-step flow)    │   │                      │
│                                │  └──────────────────┘   │                      │
│                                │  ┌──────────────────┐   │                      │
│                                │  │  x402 Payment     │   │                      │
│                                │  │  Gate + Escrow    │   │                      │
│                                │  └──────────────────┘   │                      │
│                                │  ┌──────────────────┐   │                      │
│                                │  │  Payment Hub      │   │                      │
│                                │  │  (Ledger + MCP)   │   │                      │
│                                │  └──────────────────┘   │                      │
│                                └──────────────────────────┘                      │
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────┐    │
│  │                       Persistence Layer                                  │    │
│  │  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────────┐    │    │
│  │  │   SQLite     │  │  CosmosDB    │  │  Learning + Metrics Store   │    │    │
│  │  │  (local)     │  │  (Azure)     │  │  (feedback, scores, trends) │    │    │
│  │  └─────────────┘  └──────────────┘  └─────────────────────────────┘    │    │
│  └──────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
                                         │
              ┌──────────────────────────┼──────────────────────────┐
              │                          │                          │
    ┌─────────▼──────────┐   ┌───────────▼──────────┐   ┌─────────▼──────────┐
    │  Azure OpenAI      │   │  Azure CosmosDB      │   │  Azure Container   │
    │  (GPT-4o)          │   │  (NoSQL persistence)  │   │  Apps + Registry   │
    └────────────────────┘   └──────────────────────┘   └────────────────────┘
```

---

## Module Descriptions

### `src/agents/` — Core Agents

| Module | Purpose |
|--------|---------|
| `ceo_agent.py` | Top-level orchestrator. Analyzes tasks, makes hiring decisions, manages budgets, delegates work. Tools: `analyze_task`, `check_budget`, `approve_hire`, `discover_tools`, `get_hiring_recommendation`. |
| `builder_agent.py` | Code generation, testing, and deployment. Handles build-type subtasks. |
| `research_agent.py` | Web research, analysis, report generation. Uses DuckDuckGo for live search. |
| `_mock_client.py` | Mock LLM client for testing. Returns structured responses without API calls. |

### `src/framework/` — Agent Framework

| Module | Purpose |
|--------|---------|
| `agent.py` | `AgentFrameworkAgent` — Microsoft Agent Framework-compatible abstraction with named agents, system prompts, MCP tool definitions, and thread state tracking. |
| `orchestrator.py` | `Orchestrator` — implements Sequential, Concurrent, and Handoff patterns. Tracks execution state, timing, and per-agent results. |
| `azure_llm.py` | Azure OpenAI integration. Connection management, health checks, graceful fallback. |
| `a2a.py` | Agent-to-agent protocol implementation for cross-agent communication. |
| `mcp_tools.py` | MCP tool registration and discovery integration. |
| `agents/` | Specialized agent implementations: `analyst.py`, `executor.py`, `researcher.py`. |

### `src/marketplace/` — Agent Marketplace

| Module | Purpose |
|--------|---------|
| `__init__.py` | `MarketplaceRegistry` + `SkillMatcher` — agent registration, capability indexing, search by skill/price. Pre-registers internal agents (builder, research) and demo external agents. |
| `x402.py` | x402 V2 payment protocol. `X402PaymentGate` generates 402 responses, verifies payment proofs. `AgentEscrow` manages hold → release/refund lifecycle. |
| `hiring.py` | `HiringManager` — 7-step hiring flow: discover → select → negotiate → escrow → assign → verify → release. `BudgetTracker` enforces per-task spending limits. |

### `src/mcp_servers/` — MCP Server Implementations

| Module | Purpose |
|--------|---------|
| `registry_server.py` | MCP server for agent discovery. Tools: `discover_agents`, `register_agent`, `list_agents`, `discover_external_agents`. |
| `payment_hub.py` | MCP server for financial operations. `PaymentLedger` tracks all transactions. Tools: `allocate_budget`, `check_budget`, `pay_agent`, `get_spending_report`. |
| `a2a_server.py` | Agent-to-agent protocol MCP server. |
| `tool_server.py` | MCP tool registration and management server. |

### `src/persistence/` — Storage

| Module | Purpose |
|--------|---------|
| `cosmos.py` | Azure Cosmos DB adapter. Containers: `agents`, `jobs`, `payments`. Methods for CRUD + health checks. Graceful degradation when unavailable. |

### `src/storage.py` — SQLite Persistence

Local SQLite database with tables:
- `tasks` — task lifecycle (id, description, workflow, budget, status, result)
- `payments` — transaction ledger (from, to, amount, tx_hash, status)
- `agents` — registered agents (name, skills, price, endpoint, protocol)
- `budgets` — per-task budget tracking (allocated, spent)
- `tools` — registered MCP tools
- `metrics` — event-level metrics (agent_id, task_type, cost, latency)

### `src/api/` — REST API

FastAPI application with endpoints for task management, agent listing, payment history, metrics, health checks, and demo mode. Includes CORS middleware, background task execution, and optional dashboard static file serving.

### `src/metrics/` — Observability

| Module | Purpose |
|--------|---------|
| `collector.py` | Event-level metrics collection. System-wide and per-agent summaries. |
| `analytics.py` | `CostAnalyzer` — cost by agent, by task type, efficiency scoring, trend analysis. `ROICalculator` — savings estimates, best-value agent identification. |

### `src/learning/` — Adaptive Optimization

| Module | Purpose |
|--------|---------|
| `feedback.py` | `FeedbackRecord` — capture task outcomes with quality scores, latency, and cost. |
| `scorer.py` | `AgentScore` — composite scoring with components: success rate, cost efficiency, latency, recency. Exponential decay weights recent performance. |
| `optimizer.py` | Thompson sampling optimizer. Balances exploration vs exploitation for agent hiring. Provides recommendations with confidence bounds. |

---

## Orchestration Patterns

### Sequential Pipeline

```
Task → [Research Agent] → [CEO Decision] → [Builder Agent] → [Deploy] → Result
```

Agents execute in order, each receiving the output of the previous step. The CEO agent makes go/no-go decisions between stages.

### Concurrent Execution

```
         ┌→ [Agent A] ─┐
Task ────┤              ├→ [CEO merges results] → Result
         └→ [Agent B] ─┘
```

Independent subtasks run in parallel. Results are collected and synthesized by the CEO.

### Group Chat

```
         ┌─────────────────────────────┐
         │        Shared Context       │
         │                             │
         │  CEO ←→ Builder ←→ Research │
         │                             │
         └─────────────────────────────┘
```

Multi-agent collaboration with shared message history. CEO coordinates, agents propose solutions, terminates when task completion signal is detected.

### Handoff

```
CEO → [Specialist A] → result → CEO → [Specialist B] → result → CEO
```

Dynamic delegation where agents hand control back to the coordinator with their results.

---

## x402 Payment Flow

The x402 protocol enables HTTP-native payments between agents:

```
Step 1: CEO requests service from external agent
           │
Step 2: Agent responds with HTTP 402 Payment Required
           │    Body: { "accepts": [{
           │      "scheme": "exact",
           │      "network": "eip155:8453",        ← Base mainnet
           │      "maxAmountRequired": "5000000",   ← $5.00 USDC (6 decimals)
           │      "payTo": "0xAgent...",
           │      "requiredDeadlineSeconds": 300,
           │      "extra": {
           │        "name": "USDC",
           │        "facilitatorUrl": "https://facilitator.payai.network"
           │      }
           │    }]}
           │
Step 3: CEO creates escrow hold
           │    amount reserved from task budget
           │
Step 4: CEO generates EIP-712 signed payment
           │    sent to facilitator for verification
           │
Step 5: Facilitator verifies signature + funds
           │
Step 6: Agent executes the task
           │
Step 7: CEO verifies result quality
           │
Step 8: Escrow released → USDC transferred on-chain
           │    (or refunded if task failed)
           │
Step 9: Transaction recorded in payment ledger + metrics
```

**Supported Networks**: Base (eip155:8453), SKALE, Arbitrum
**Asset**: USDC (6 decimal places)
**Facilitator**: https://facilitator.payai.network

---

## Azure Integration

### Services Used

| Service | Role | Module |
|---------|------|--------|
| **Azure OpenAI (GPT-4o)** | LLM intelligence for all agents | `src/framework/azure_llm.py` |
| **Azure Cosmos DB** | NoSQL persistence for agents, tasks, payments | `src/persistence/cosmos.py` |
| **Azure Container Apps** | Production microservice deployment | `scripts/deploy.sh` |
| **Azure Container Registry** | Docker image storage | Deployment pipeline |
| **Azure Application Insights** | Telemetry, tracing, monitoring | OpenTelemetry integration |

### Health Monitoring

`GET /health/azure` probes each Azure service and returns status:

```json
{
  "status": "healthy",
  "services": {
    "azure_openai": { "connected": true, "model": "gpt-4o" },
    "cosmos_db": { "connected": true, "containers": 3 }
  }
}
```

The system degrades gracefully — if Azure OpenAI is unavailable, it falls back to mock or Ollama. If CosmosDB is unavailable, it uses local SQLite.

---

## Security Model

### Credential Isolation
- All credentials stored in `/credentials/` directory (mode 600, gitignored)
- Per-provider credential loading via environment variables or `.env` file
- No credentials in source code, logs, or API responses

### Input Validation
- Pydantic models validate all API inputs (type checking, length limits, range constraints)
- Task descriptions limited to 2000 characters
- Budget capped at configurable maximum ($1000 default)

### Rate Limiting
- Budget enforcement prevents runaway spending
- Per-task budget allocation with hard caps
- Escrow system ensures funds are reserved before work begins

### Payment Security
- EIP-712 typed signatures for payment authorization
- Facilitator-verified transactions (not direct peer-to-peer)
- Escrow holds with explicit release/refund lifecycle
- Full audit trail in payment ledger

---

## Data Flow Example: Hiring an External Agent

```
1. User: POST /tasks {"description": "Design a logo", "budget": 10.0}
2. CEO: analyze_task() → task_type=design, needs external agent
3. CEO: discover_agents(capability="design") → finds "designer-ext-001" at $5/call
4. CEO: check_budget() → $10 allocated, $0 spent, $10 remaining
5. CEO: approve_hire("designer-ext-001", price=5.0, max_budget=10.0) → approved
6. Escrow: hold_payment(payer="ceo", payee="designer-ext-001", amount=5.0) → escrow_id
7. x402: create_402_response() → payment gate for external agent
8. External Agent: executes task, returns result
9. CEO: verify result quality → passes
10. Escrow: release_on_completion(escrow_id) → USDC transferred
11. Ledger: record_payment(from="ceo", to="designer-ext-001", amount=5.0)
12. Learning: record_feedback(agent="designer-ext-001", outcome="success", quality=0.9)
13. Metrics: update_metrics(cost=5.0, latency=2300ms, status="success")
```

---

## Configuration

All settings are managed via environment variables or `.env` file:

```bash
# Model provider
MODEL_PROVIDER=azure_ai                        # mock, azure_ai, ollama, openai

# Azure OpenAI
AZURE_AI_PROJECT_ENDPOINT=https://...          # Azure endpoint
AZURE_AI_MODEL_DEPLOYMENT=gpt-4o              # Model name

# x402 payments
X402_FACILITATOR_URL=https://facilitator.payai.network
X402_NETWORK=eip155:8453                       # Base mainnet
X402_RECEIVER_ADDRESS=0x...                    # Payment receiver
WALLET_ADDRESS=0x...                           # Agent wallet

# Budget
MAX_BUDGET_USD=100.0                           # Maximum spending limit

# Server
API_HOST=0.0.0.0
API_PORT=8080
```

---

## Test Coverage

683 tests across 21 test files covering:

| Area | Tests | What's Covered |
|------|-------|----------------|
| Agent behavior | `test_agents.py` | CEO task analysis, builder/research execution, mock client |
| Orchestration | `test_workflows.py` | Sequential, concurrent, group chat patterns |
| Framework | `test_framework.py` | Agent abstraction, thread state, tool definitions |
| Hiring | `test_agent_hiring.py` | Full 7-step hiring flow, budget tracking, escrow |
| Marketplace | `test_marketplace.py` | Registry, skill matching, agent cards |
| x402 | `test_marketplace.py` | 402 responses, payment verification, escrow lifecycle |
| Persistence | `test_storage.py` | SQLite CRUD, budget tracking, transaction queries |
| CosmosDB | `test_cosmos.py` | Azure persistence, health checks |
| API | `test_dashboard_api.py` | All REST endpoints, request/response validation |
| Metrics | `test_metrics.py` | Collection, analytics, cost analysis |
| Learning | `test_learning.py` | Feedback, scoring, Thompson sampling |
| Demo | `test_demo_scenarios.py` | End-to-end scenario execution |
| A2A | `test_a2a_server.py` | Agent-to-agent protocol |
| Tools | `test_tool_server.py` | MCP tool registration |
| Azure | `test_azure_health.py`, `test_azure_llm.py` | Service connectivity |
