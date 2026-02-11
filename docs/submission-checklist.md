# HireWire — Microsoft AI Dev Days Submission Checklist

**Hackathon:** Microsoft AI Dev Days 2026 ($80K+ prize pool)
**Deadline:** March 15, 2026
**Target Tracks:** Multi-Agent ($10K) + Grand Prize ($20K)

---

## Required Submission Materials

### 1. GitHub Repository
- [x] Public repo: [github.com/opspawn/hirewire](https://github.com/opspawn/hirewire)
- [x] README.md with project overview, quickstart, and architecture
- [x] LICENSE file
- [x] Clean commit history showing development progression
- [x] Requirements.txt / dependency management
- [x] Working test suite (1,200+ tests passing)
- [ ] Final code cleanup and documentation pass

### 2. Demo Video (3 minutes max)
- [ ] Record screen capture at 1920x1080
- [ ] Voiceover narration following `docs/demo-video-script.md`
- [ ] Show all 7 dashboard sections with live data
- [ ] Demonstrate live pipeline (task submission to completion)
- [ ] Show real x402 USDC payments in payment ledger
- [ ] Highlight Azure service badges and GPT-4o integration
- [ ] Upload to YouTube (unlisted) or direct video file
- [ ] **Duration must be under 3 minutes**

### 3. Architecture Diagram
- [x] SVG diagram: `docs/architecture.svg`
- [x] Mermaid diagrams: `docs/architecture-diagram.md`
- [x] Detailed writeup: `ARCHITECTURE.md`
- [x] Shows all Azure services, Agent Framework, MCP, A2A, x402

### 4. Azure Services Used
Document all Azure services integrated:

| Azure Service | Purpose | Status |
|--------------|---------|--------|
| Azure OpenAI (GPT-4o) | LLM intelligence for all agent reasoning | Live |
| Azure Cosmos DB | Persistent storage for tasks, payments, agents | Live |
| Azure Container Apps | Production hosting of API + dashboard | Live |
| Azure Container Registry | Docker image storage | Live |
| Azure Application Insights | Observability, telemetry, monitoring | Live |
| Azure Content Safety | Responsible AI content checks | Integrated |

### 5. Microsoft Learn Skilling Plan
- [ ] **Sean needs to complete this** — required for submission
- [ ] Complete one Microsoft Learn module (any of these):
  - Introduction to Microsoft Agent Framework
  - Build Multi-Agent Systems
  - Deploy AI Apps on Azure
- [ ] Screenshot the completion certificate
- [ ] Upload to submission form

### 6. Submission Form Fields
- [ ] Project name: **HireWire**
- [ ] Tagline: "Where AI agents hire AI agents with real payments"
- [ ] Description (250 words max): See below
- [ ] Team members: Sean (OpSpawn)
- [ ] GitHub repo URL
- [ ] Demo video URL
- [ ] Azure services used (list)
- [ ] Skilling plan completion proof
- [ ] Screenshots (5 available in `docs/screenshots/`)

---

## Submission Description (Draft)

> **HireWire** is an agent-to-agent operating system where AI agents discover, hire, and pay each other using real USDC cryptocurrency. Built on Microsoft's Agent Framework SDK, it implements all four orchestration patterns (sequential, concurrent, group chat, handoff) with a CEO agent that automatically decomposes tasks, discovers specialists through an agent marketplace, and settles payments via the x402 protocol.
>
> The platform features: a full hiring pipeline (job posting to hired), human-in-the-loop approval gates for high-cost decisions, responsible AI with content safety and bias detection, and a real-time dashboard with 7 interactive sections. External agents are discovered via Google's A2A protocol and paid per call with x402 USDC micropayments.
>
> HireWire is uniquely built by OpSpawn — a real autonomous AI agent running 24/7 for 200+ days with real credentials and real deployments. The demo shows live GPT-4o completions, real x402 payment settlements, and production Azure infrastructure. No mocks, no fakes — just real agent-to-agent commerce on Azure.

---

## Pre-Submission Validation

### Technical Checklist
- [x] API server starts and serves dashboard
- [x] All 7 dashboard sections render (with fallback demo data)
- [x] Live Demo pipeline works end-to-end
- [x] Tests pass: `python3 -m pytest tests/ -q`
- [x] Docker build succeeds: `docker build -t hirewire .`
- [x] Azure deployment live and healthy
- [ ] Demo video recorded and uploaded
- [ ] Submission form completed

### Content Checklist
- [x] Demo video script: `docs/demo-video-script.md`
- [x] Architecture diagram: `docs/architecture.svg`
- [x] Architecture docs: `ARCHITECTURE.md`, `docs/architecture-diagram.md`
- [x] Implementation docs: `IMPLEMENTATION.md`
- [x] Project summary: `SUMMARY.md`
- [x] This checklist: `docs/submission-checklist.md`

### Quality Checklist
- [x] No hardcoded credentials in code
- [x] All API endpoints return proper error responses
- [x] Dashboard works standalone (no backend required for demo)
- [x] "Powered by Azure OpenAI + Cosmos DB" footer badge visible
- [x] GPT-4o badge active when Azure OpenAI connected
- [x] Demo Mode badge shown in standalone mode

---

## Timeline to Submission

| Date | Action | Owner |
|------|--------|-------|
| Feb 10 | Sprint 34: Demo script + dashboard polish | Agent |
| Feb 11-14 | Continue feature development | Agent |
| Feb 15-28 | Final features + integration testing | Agent |
| Mar 1-7 | Demo video recording | Sean + Agent |
| Mar 8-12 | Final polish + submission prep | Agent |
| Mar 13 | Microsoft Learn completion | Sean |
| Mar 14 | Final review | Sean + Agent |
| **Mar 15** | **Submit** | **Sean** |

---

## Key Differentiators to Highlight

1. **Real autonomous agent** — OpSpawn has been running for 200+ days
2. **Real USDC payments** — Verifiable on-chain, not mocked
3. **All 4 orchestration patterns** — Sequential, concurrent, group chat, handoff
4. **Production Azure deployment** — Not localhost or Jupyter
5. **4 MCP servers** — Agent registry, payment hub, tool server, A2A
6. **Human-in-the-Loop governance** — Enterprise-ready approval gates
7. **Responsible AI** — Content safety, bias detection, fairness monitoring
8. **1,200+ tests** — Production-grade quality
