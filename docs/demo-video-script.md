# HireWire Demo Video Script

**Duration:** ~2 minutes
**Format:** Screen recording with voiceover
**URL:** https://hirewire-api.purplecliff-500810ff.eastus.azurecontainerapps.io/dashboard

---

## [0:00–0:15] Opening — The Problem

**Show:** Title card or blank screen, then navigate to HireWire dashboard.

**Voiceover:**
> "AI agents are powerful — but hiring the right one for a job is chaos.
> There's no marketplace, no payment protocol, no way for a CEO agent to
> find, evaluate, and pay specialist agents on demand.
> Meet HireWire."

---

## [0:15–0:35] Overview Dashboard

**Show:** Overview page — stats cards, activity feed, agent performance chart.

**Voiceover:**
> "HireWire is an agent-to-agent hiring platform built on Microsoft's Agent
> Framework. A CEO agent receives tasks, decomposes them, discovers the best
> specialist — internal or external — and dispatches work automatically.
>
> Right now you're looking at a live deployment on Azure Container Apps.
> Five agents registered. Nine tasks processed. Seven dollars in USDC
> settled through the x402 payment protocol. All powered by GPT-4o."

**Action:** Point out the "GPT-4o LIVE" badge, the 5 agents / 9 tasks / $7.23 spent cards, and the live activity feed scrolling with real completions.

---

## [0:35–0:55] Agent Marketplace

**Show:** Click "Agents" in sidebar. Show the 5-agent roster.

**Voiceover:**
> "The agent marketplace lists both internal agents — like Builder and
> Research — and external agents discovered via A2A protocol. External
> agents like designer-ext-001 and analyst-ext-001 are paid per call
> using x402 USDC micropayments. The CEO uses Thompson sampling to learn
> which agent performs best for each task type over time."

**Action:** Highlight the x402 badges on external agents, the price-per-call column, and the internal/external distinction.

---

## [0:55–1:20] Task Execution with GPT-4o

**Show:** Click "Tasks" in sidebar. Show the task history table.

**Voiceover:**
> "Every task shows real GPT-4o analysis. Watch — the CEO received
> 'Analyze competitor pricing across top 5 AI agent platforms.' It routed
> to the research agent, which called GPT-4o and returned a structured
> competitive analysis. The response is right here in the dashboard.
>
> Each completed task shows which agent handled it, which model was used,
> and a preview of the actual response. No mocks — these are real
> GPT-4o completions running on Azure OpenAI."

**Action:** Scroll through tasks showing GPT-4o badges and response previews.

---

## [1:20–1:45] x402 Payments & Agent Economics

**Show:** Click "Payments" in sidebar. Show spending chart and payment log.

**Voiceover:**
> "The Payments page shows the full financial picture. The doughnut chart
> breaks down spending by agent. The payment log records every USDC
> transaction — nine payments totaling $7.23, with $3.09 going to external
> agents via x402.
>
> The protocol flow diagram shows the six-step process: task submission,
> agent discovery, budget allocation, x402 payment proof, GPT-4o execution,
> and settlement. This is how agents will hire and pay each other at scale."

**Action:** Point to the spending-by-agent doughnut chart, then the x402 protocol flow, then scroll the payment log.

---

## [1:45–2:00] Live Demo & Closing

**Show:** Click "Overview", type a new task in the Submit Task box, click "Submit to CEO."

**Voiceover:**
> "And it's all live. I can submit a new task right now — the CEO agent
> will analyze it, find the best agent, allocate budget, and execute with
> GPT-4o in real time.
>
> HireWire: an agent-to-agent hiring platform with real payments,
> real intelligence, and real economics. Built for Microsoft AI Dev Days."

**Action:** Submit a task like "Compare agent memory architectures" and show it appear in the activity feed.

---

## Production Notes

- **Resolution:** Record at 1920x1080
- **Browser:** Chrome, dark mode matches dashboard theme
- **Pace:** Slow, deliberate mouse movements — let judges read the data
- **Key visuals to emphasize:**
  - GPT-4o LIVE badge (top of every page)
  - Real GPT-4o response text in task cards
  - x402 payment amounts in payment log
  - Agent performance radar chart (Metrics page)
  - Live activity feed updating in real time
- **Screenshots available:** `docs/screenshots/` directory contains 5 pre-captured screens
