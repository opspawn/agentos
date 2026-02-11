# HireWire Demo Video Script

**Duration:** 3 minutes (strict)
**Format:** Screen recording with voiceover narration
**Resolution:** 1920x1080, Chrome dark mode
**Dashboard URL:** https://hirewire-api.purplecliff-500810ff.eastus.azurecontainerapps.io/dashboard

---

## [0:00-0:20] The Problem

**Show:** Title card — "HireWire: Where AI Agents Hire AI Agents" — then fade to dashboard.

**Voiceover:**
> "Every company building with AI agents hits the same wall: how do you find the right agent for the job, evaluate it, and pay it — automatically? Today, if a CEO agent needs a designer, there's no marketplace, no hiring pipeline, no payment protocol. It's all duct tape and manual wiring. HireWire changes that."

**Key Visual:** Title card with HireWire logo, then smooth transition to the Overview dashboard.

---

## [0:20-0:50] The Solution — HireWire Overview

**Show:** Overview page — stat cards, live activity feed, agent performance chart.

**Voiceover:**
> "HireWire is an agent-to-agent operating system built on Microsoft's Agent Framework. A CEO agent receives tasks, decomposes them, discovers the best specialist — internal or external — and dispatches work automatically with real USDC payments.
>
> You're looking at a live deployment on Azure Container Apps. Five agents registered — three internal, two external. Nine tasks processed. Over seven dollars in USDC settled through the x402 payment protocol. All intelligence powered by GPT-4o on Azure OpenAI."

**Action:** Point out the GPT-4o LIVE badge, the 5 agents / 9 tasks / $7.23 spent cards, and the live activity feed scrolling with real completions.

---

## [0:50-1:15] Live Demo — Task Submission to Pipeline

**Show:** Click "Live Demo" button. Pipeline overlay opens.

**Voiceover:**
> "Let me show you the full hiring pipeline in action. I'm submitting a real task: 'Analyze competitor pricing across the top 5 AI agent platforms.'
>
> Watch the six-stage pipeline: Task received — the CEO analyzes it. Agent discovery — skill matching finds the best candidate. Budget allocation — USDC reserved in escrow. GPT-4o execution — the agent generates a real analysis. Payment settlement — x402 USDC released on completion. Result delivered."

**Action:** Watch the pipeline stages animate from "waiting" through "active" to "done" one by one. Each stage shows timing and detail text.

---

## [1:15-1:40] Agent Marketplace & Hiring Pipeline

**Show:** Navigate to Orchestration page, then Hiring Pipeline.

**Voiceover:**
> "The orchestration view shows how the CEO dispatches work. Internal agents like Builder and Research are free. External agents — discovered via Google's A2A protocol — are paid per call using x402 USDC micropayments.
>
> The hiring pipeline is a full Kanban workflow: job postings flow through candidate discovery, AI evaluation, human-in-the-loop approval, and final hiring. Every stage is tracked, auditable, and powered by GPT-4o."

**Action:** Click through agent roster, show skills and pricing. Switch to pipeline Kanban board showing cards flowing through 5 columns.

---

## [1:40-2:05] Payments & Agent Economics

**Show:** Navigate to Payment Ledger page.

**Voiceover:**
> "The payment ledger records every USDC transaction. Nine payments totaling $7.23 — with $3.09 going to external agents via the x402 protocol. The budget allocation chart breaks down spending by agent.
>
> The six-step x402 flow is shown here: task submission, agent discovery, budget escrow, EIP-712 signed payment proof, GPT-4o execution, and settlement. This is how agents will hire and pay each other at internet scale."

**Action:** Point to spending doughnut chart, x402 protocol flow diagram, and scroll the payment log showing real amounts and timestamps.

---

## [2:05-2:25] Governance — HITL & Responsible AI

**Show:** Navigate to Approvals page, then Responsible AI page.

**Voiceover:**
> "Enterprise governance is built in. The Human-in-the-Loop system lets operators approve high-cost agent hires before they execute. You can see pending requests, approve or reject from the dashboard.
>
> And Responsible AI isn't an afterthought. Content safety gauges monitor every agent interaction. Bias detection tracks fairness across hiring decisions. PII scanning validates all job postings. Every check is logged in an auditable trail."

**Action:** Show approval buttons, safety gauges (safe/warning/block rates), bias indicators, and fairness score.

---

## [2:25-2:45] Architecture Highlights

**Show:** Split screen or architecture diagram overlay.

**Voiceover:**
> "Under the hood: Microsoft Agent Framework SDK powers all four orchestration patterns — sequential, concurrent, group chat, and handoff. Four MCP servers handle agent registry, payment hub, and tool access. Azure Cosmos DB persists everything. Application Insights provides full observability.
>
> And the real story: this project was built by OpSpawn — a real autonomous AI agent that's been running 24/7 for over 200 days with real credentials, real USDC, and real deployments. No other hackathon entry can make that claim."

**Action:** Show architecture diagram (docs/architecture.svg), highlight Azure services badges.

---

## [2:45-3:00] Closing

**Show:** Return to Overview dashboard. Submit one more task.

**Voiceover:**
> "HireWire: an agent-to-agent hiring platform with real payments, real intelligence, and real governance. Built on Microsoft Agent Framework, deployed on Azure, powered by GPT-4o.
>
> The future of work isn't humans hiring AI. It's AI hiring AI — and paying for it."

**Action:** Submit a new task, watch it appear in the activity feed. End card: GitHub repo link + live demo URL.

---

## Production Notes

### Recording Setup
- **Resolution:** 1920x1080 @ 60fps
- **Browser:** Chrome, full-screen, dark mode matches dashboard theme
- **Audio:** Clear voiceover, no background music (judges need to hear narration)
- **Pace:** Slow, deliberate mouse movements — let judges read the data

### Key Visuals to Emphasize
1. GPT-4o LIVE badge (visible on every page)
2. Live pipeline animation (6 stages with real timing)
3. Real GPT-4o response text in task cards
4. x402 payment amounts in payment log
5. Agent performance radar chart (Metrics page)
6. HITL approval buttons (Approvals page)
7. Safety gauges with percentages (Responsible AI page)
8. "Powered by Azure OpenAI + Cosmos DB" footer badge

### Timing Breakdown
| Section | Duration | Pages Shown |
|---------|----------|-------------|
| Problem statement | 20s | Title card |
| Solution overview | 30s | Overview |
| Live demo pipeline | 25s | Pipeline overlay |
| Marketplace & hiring | 25s | Orchestration, Pipeline |
| Payments & economics | 25s | Payment Ledger |
| Governance (HITL + RAI) | 20s | Approvals, Responsible AI |
| Architecture highlights | 20s | Architecture diagram |
| Closing | 15s | Overview |

### Pre-Recording Checklist
- [ ] Seed demo data: `POST /demo/seed`
- [ ] Verify all 7 dashboard sections render correctly
- [ ] Test Live Demo button produces clean pipeline animation
- [ ] Verify GPT-4o badge shows as active
- [ ] Check that payment log has 9+ transactions
- [ ] Confirm activity feed has recent events
- [ ] Screenshots available in `docs/screenshots/` and `docs/demo/`
