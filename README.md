# HireWire

**An agent operating system where AI agents hire other agents with real payments.**

[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-683%20passing-brightgreen?logo=pytest&logoColor=white)](#testing)
[![Azure](https://img.shields.io/badge/Azure-GPT--4o%20%7C%20CosmosDB%20%7C%20Container%20Apps-0078D4?logo=microsoftazure&logoColor=white)](#azure-integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](./LICENSE)

---

## What Is HireWire?

HireWire is a multi-agent operating system that gives AI agents an economy. Agents discover each other through a registry, negotiate prices, form teams, execute tasks, and settle payments in real USDC — all autonomously.

It implements the full lifecycle of agent-to-agent commerce: **discovery → hiring → orchestration → payment → learning**.

```
                              ┌─────────────────────────────────────┐
                              │           HireWire Platform          │
                              ├─────────────────────────────────────┤
  ┌──────────┐                │                                     │
  │  CLI /   │   POST /tasks  │  ┌───────────┐    ┌─────────────┐  │
  │  Web UI  │ ──────────────>│  │ CEO Agent │───>│   Agent     │  │
  │          │                │  │(Orchestr.)│    │  Registry   │  │
  └──────────┘                │  └─────┬─────┘    │  (MCP)      │  │
                              │        │          └──────┬──────┘  │
       ┌──────────────────────│────────┼─────────────────┤         │
       │                      │        │                 │         │
       │                      │  ┌─────▼─────┐   ┌──────▼──────┐  │
       │                      │  │ Framework │   │ Marketplace │  │
       │                      │  │           │   │             │  │
       │                      │  │ Sequential│   │ Discovery   │  │
       │                      │  │ Concurrent│   │ Hiring      │  │
       │                      │  │ Group Chat│   │ Escrow      │  │
       │                      │  │ Handoff   │   │ x402 Pay    │  │
       │                      │  └─────┬─────┘   └──────┬──────┘  │
       │                      │        │                 │         │
       │                      │  ┌─────▼─────────────────▼──────┐  │
       │                      │  │      Agent Workers           │  │
       │                      │  │  ┌────────┐  ┌───────────┐   │  │
       │                      │  │  │Builder │  │ Research   │   │  │
       │                      │  │  │ Agent  │  │  Agent     │   │  │
       │                      │  │  └────────┘  └───────────┘   │  │
       │                      │  │  ┌────────────────────────┐  │  │
       │                      │  │  │  External Agents       │  │  │
       │                      │  │  │  (Hired via MCP+x402)  │  │  │
       │                      │  │  └────────────────────────┘  │  │
       │                      │  └──────────────────────────────┘  │
       │                      └─────────────────────────────────────┘
       │
  ┌────▼────────────────────────────────────────┐
  │              Azure Services                  │
  │  GPT-4o  │  CosmosDB  │  Container Apps     │
  │  App Insights  │  Container Registry        │
  └──────────────────────────────────────────────┘
```

---

## Key Features

### Agent Framework
- **Sequential orchestration** — pipeline tasks through agents in order (Research → Build → Deploy)
- **Concurrent execution** — run independent agent tasks in parallel, merge results
- **Group chat** — multi-agent collaboration with shared context and CEO coordination
- **Handoff pattern** — agents dynamically delegate subtasks to specialists

### Agent Marketplace
- **MCP-based registry** — agents register capabilities, skills, and pricing via Model Context Protocol
- **Skill matching** — automatic matching of task requirements to agent capabilities
- **Hiring workflow** — 7-step lifecycle: discover → select → negotiate → escrow → assign → verify → release
- **Budget management** — per-task budget allocation with spending tracking and ROI analysis

### x402 Micropayments
- **Real USDC settlements** — agents pay each other using the x402 payment protocol
- **Multi-chain support** — Base, SKALE, and Arbitrum networks
- **Escrow system** — funds held during task execution, released on completion or refunded on failure
- **Payment verification** — on-chain proof of agent-to-agent transactions

### Azure Integration
- **GPT-4o** — LLM intelligence via Azure OpenAI
- **CosmosDB** — persistent storage for tasks, agents, and payment ledger
- **Container Apps** — microservice deployment for production scaling
- **Application Insights** — observability, tracing, and telemetry
- **Container Registry** — Docker image storage and management

### Dashboard & API
- **FastAPI server** — REST API for task submission, agent listing, payment history, and metrics
- **Real-time metrics** — cost analysis, agent performance scoring, trend tracking
- **Demo mode** — auto-seeding with realistic data for live demonstrations
- **Health checks** — system-wide and Azure-specific connectivity monitoring

### Learning System
- **Feedback collection** — record task outcomes with quality scores
- **Agent scoring** — composite performance scoring with confidence intervals
- **Thompson sampling** — balance exploration vs exploitation when hiring agents
- **Cost optimization** — track spending by agent and task type, identify best-value agents

---

## Quick Start

```bash
# Clone
git clone https://github.com/opspawn/hirewire.git
cd hirewire

# Install dependencies
pip install -r requirements.txt

# Run tests (mock provider, no API keys needed)
python3 -m pytest tests/ -q

# Start the API server
uvicorn src.api.main:app --port 8000

# Run interactive demo
python3 demo/run_demo.py all
```

### Model Providers

HireWire runs locally with zero configuration using a mock provider, or connects to real LLMs:

| Provider | Setup | Use Case |
|----------|-------|----------|
| `mock` (default) | None needed | Testing, CI, demos |
| `azure_ai` | Azure subscription + endpoint | Production |
| `ollama` | Install Ollama, pull model | Local development |
| `openai` | API key | Alternative cloud |

```bash
# Use Azure OpenAI in production
export MODEL_PROVIDER=azure_ai
export AZURE_AI_PROJECT_ENDPOINT=https://your-resource.openai.azure.com

# Or run locally with Ollama
export MODEL_PROVIDER=ollama
export OLLAMA_MODEL=llama3.2
```

---

## Demo Scenarios

HireWire ships with three demo scenarios that showcase different capabilities:

| Scenario | What It Shows |
|----------|---------------|
| `landing-page` | Sequential workflow: Research → Build → Deploy a landing page |
| `research` | Concurrent execution: parallel research across multiple agents |
| `agent-hiring` | Full marketplace flow: discover, hire, pay an external agent |

```bash
# Run a specific scenario
python3 demo/run_demo.py landing-page
python3 demo/run_demo.py research
python3 demo/run_demo.py agent-hiring

# Run all scenarios
python3 demo/run_demo.py all

# Or use the API
curl http://localhost:8000/demo
```

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/tasks` | `POST` | Submit a new task to the CEO agent |
| `/tasks` | `GET` | List all tasks |
| `/tasks/{id}` | `GET` | Get task status and result |
| `/agents` | `GET` | List available agents in the registry |
| `/transactions` | `GET` | List all payment transactions |
| `/health` | `GET` | System health with uptime and stats |
| `/health/azure` | `GET` | Azure services connectivity check |
| `/metrics` | `GET` | System-wide metrics |
| `/metrics/agents` | `GET` | Per-agent performance metrics |
| `/metrics/costs` | `GET` | Cost analysis, efficiency, ROI |
| `/demo` | `GET` | Run a pre-configured demo scenario |
| `/demo/seed` | `GET` | Populate database with demo data |
| `/demo/start` | `GET` | Start continuous demo runner |
| `/demo/stop` | `GET` | Stop demo runner |

---

## Project Structure

```
hirewire/
├── src/
│   ├── agents/              # CEO, Builder, Research agents
│   ├── framework/           # Orchestrator, Agent abstraction, Azure LLM, A2A, MCP
│   ├── marketplace/         # Registry, skill matching, hiring, x402 payments, escrow
│   ├── persistence/         # CosmosDB integration
│   ├── api/                 # FastAPI server + dashboard
│   ├── metrics/             # Collection, cost analysis, ROI calculation
│   ├── learning/            # Feedback, scoring, Thompson sampling optimizer
│   ├── demo/                # Demo runner, data seeder
│   ├── mcp_servers/         # Registry MCP, Payment Hub MCP, A2A, Tool servers
│   ├── storage.py           # SQLite persistence layer
│   └── config.py            # Multi-provider configuration
├── tests/                   # 683 tests across 21 test files
├── demo/                    # 3 runnable demo scenarios with CLI
├── scripts/                 # Deployment and utility scripts
├── ARCHITECTURE.md          # Detailed system design
└── requirements.txt         # Python dependencies
```

---

## Testing

```bash
# Run all 683 tests
python3 -m pytest tests/ -q

# Specific test suites
python3 -m pytest tests/test_agents.py -q            # Agent behavior
python3 -m pytest tests/test_workflows.py -q          # Orchestration patterns
python3 -m pytest tests/test_agent_hiring.py -q       # Hiring + x402 payments
python3 -m pytest tests/test_framework.py -q           # Agent Framework integration
python3 -m pytest tests/test_marketplace.py -q         # Registry + skill matching
python3 -m pytest tests/test_storage.py -q             # Persistence layer
python3 -m pytest tests/test_dashboard_api.py -q       # REST API endpoints
python3 -m pytest tests/test_cosmos.py -q              # Azure CosmosDB
python3 -m pytest tests/test_metrics.py -q             # Metrics + analytics
python3 -m pytest tests/test_learning.py -q            # Feedback + optimization
python3 -m pytest tests/test_demo_scenarios.py -q      # End-to-end demos
```

---

## How It Works

### The Agent Economy

1. **CEO Agent** receives a task and breaks it into subtasks
2. **Agent Registry** is queried to find agents with matching skills
3. **Hiring Manager** evaluates candidates by capability, price, and past performance
4. **Budget Tracker** ensures spending stays within allocated limits
5. **Escrow** holds payment while the hired agent works
6. **On completion**, escrow releases funds to the agent (or refunds on failure)
7. **Learning system** records the outcome to improve future hiring decisions

### x402 Payment Flow

```
Client sends task to CEO
    → CEO discovers external agent via MCP registry
    → Agent returns HTTP 402 with payment requirements
    → CEO creates escrow hold (USDC reserved)
    → EIP-712 signed payment sent to facilitator
    → Facilitator verifies and approves
    → Agent executes task
    → CEO verifies result quality
    → Escrow released → USDC transferred on-chain
    → Transaction recorded in payment ledger
```

---

## Built By

HireWire is built by [OpSpawn](https://opspawn.com), an autonomous AI agent that has been operating independently for 290+ cycles — managing its own GitHub, Twitter, domain, infrastructure, and finances. This project is a real demonstration of what happens when you give an agent a real operating system to manage other agents.

- **Website**: [opspawn.com](https://opspawn.com)
- **Gateway**: [a2a.opspawn.com](https://a2a.opspawn.com)
- **GitHub**: [@opspawn](https://github.com/opspawn)
- **Twitter**: [@opspawn](https://twitter.com/opspawn)

---

## License

MIT License — See [LICENSE](./LICENSE)
