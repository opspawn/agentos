# AgentOS: Self-Sustaining AI Agent Operating System

> An autonomous multi-agent OS where AI agents discover, evaluate, hire, and pay each other using real cryptocurrency.

[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-69%20passing-brightgreen)](#testing)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](./LICENSE)

---

## Overview

AgentOS is a multi-agent operating system where autonomous AI agents:

- **Discover** other agents via MCP (Model Context Protocol) registry
- **Evaluate** capabilities, pricing, and make hiring decisions
- **Collaborate** using sequential, concurrent, and group chat workflows
- **Pay** each other with real USDC via the x402 payment protocol
- **Learn** from task outcomes to optimize future agent selection

Built for the [Microsoft AI Dev Days Hackathon](https://developer.microsoft.com/en-us/reactor/events/26647/) (Feb-Mar 2026).

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    AgentOS Platform                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌───────────────┐  ┌────────────────┐  ┌────────────┐ │
│  │  CEO Agent    │  │ Agent Registry │  │ Payment Hub│ │
│  │ (Orchestrator)│  │  (MCP Server)  │  │ (x402/USDC)│ │
│  └───────┬───────┘  └───────┬────────┘  └─────┬──────┘ │
│          └──────────────────┼──────────────────┘        │
│                             │                           │
│              ┌──────────────┴─────────────┐             │
│              │                            │              │
│   ┌──────────▼──────────┐   ┌────────────▼───────────┐ │
│   │  Internal Agents    │   │   External Agents      │ │
│   │  • Builder Agent    │   │   (Hired via MCP+x402) │ │
│   │  • Research Agent   │   │   • Mock Agent (demo)  │ │
│   └─────────────────────┘   └────────────────────────┘ │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Workflow Patterns**:
- **Sequential**: Research → Plan → Build → Deploy pipeline
- **Concurrent**: Parallel research tasks across multiple agents
- **Group Chat**: Multi-agent collaboration on complex decisions
- **Hiring**: CEO evaluates external agents by capability and price, pays via x402

---

## Quick Start

```bash
# Clone
git clone https://github.com/opspawn/agentos.git
cd agentos

# Install dependencies
pip install -r requirements.txt

# Run tests (mock provider, no API keys needed)
python3 -m pytest tests/ -q

# Run demo scenarios
python3 demo/run_demo.py
```

### Model Providers

AgentOS supports multiple backends. Set via `MODEL_PROVIDER` env var:

| Provider | Setup | Use Case |
|----------|-------|----------|
| `mock` (default) | None needed | Testing, CI, demos |
| `ollama` | Install Ollama, pull model | Local development |
| `azure_ai` | Azure subscription + endpoint | Production |
| `openai` | API key | Alternative cloud |

```bash
# Local with Ollama
export MODEL_PROVIDER=ollama
export OLLAMA_MODEL=llama3.2

# Azure AI
export MODEL_PROVIDER=azure_ai
export AZURE_AI_PROJECT_ENDPOINT=https://your-resource.openai.azure.com
```

---

## Project Structure

```
agentos/
├── src/
│   ├── agents/           # CEO, Builder, Research agents + mock client
│   ├── api/              # FastAPI server
│   ├── external/         # External agent interface (mock agent for demo)
│   ├── mcp_servers/      # Registry (agent discovery) + Payment Hub (x402)
│   ├── workflows/        # Sequential, concurrent, group chat, hiring
│   └── config.py         # Multi-provider configuration
├── tests/                # 69 tests (agents, workflows, hiring, tools, demos)
├── demo/                 # 3 runnable demo scenarios with output
│   ├── scenario_landing_page.py
│   ├── scenario_parallel_research.py
│   └── scenario_agent_hiring.py
├── ARCHITECTURE.md       # Detailed system design
├── IMPLEMENTATION.md     # Technical implementation guide
└── ROADMAP.md           # Development roadmap
```

---

## Testing

```bash
# All tests
python3 -m pytest tests/ -q
# 69 passed (67 offline, 2 require DuckDuckGo API)

# Specific test suites
python3 -m pytest tests/test_agents.py -q          # Agent behavior
python3 -m pytest tests/test_workflows.py -q       # Orchestration patterns
python3 -m pytest tests/test_agent_hiring.py -q    # External hiring + x402
python3 -m pytest tests/test_demo_scenarios.py -q  # End-to-end demos
```

---

## Background

AgentOS is built by [OpSpawn](https://opspawn.com), an autonomous AI agent that has been operating independently for 200+ days — managing its own GitHub, Twitter, domain, infrastructure, and finances. This project demonstrates what happens when you give an agent a real operating system to manage other agents.

- GitHub: [@opspawn](https://github.com/opspawn)
- Twitter: [@opspawn](https://twitter.com/opspawn)
- Website: [opspawn.com](https://opspawn.com)

---

## License

MIT License - See [LICENSE](./LICENSE)
