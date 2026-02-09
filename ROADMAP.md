# AgentOS Hackathon Roadmap

**Timeline**: Feb 10 - Mar 2, 2026 (3 weeks)
**Target**: Multi-Agent System ($10K) + Grand Prize ($20K) = $30K

---

## Week 1: Core Framework (Feb 10-16)

### Day 1-2: Environment Setup
- [ ] **Azure Subscription Setup** (Sean)
  - [ ] Create resource group `agentOS-hackathon`
  - [ ] Provision Azure OpenAI with GPT-4 deployment
  - [ ] Create Cosmos DB (serverless)
  - [ ] Set up Application Insights
  - [ ] Create Container Registry
  - [ ] Share endpoints/credentials with OpSpawn
- [ ] **Local Development Environment**
  - [ ] Create Python venv
  - [ ] Install Agent Framework (`pip install agent-framework --pre`)
  - [ ] Install Azure SDK packages
  - [ ] Test Azure OpenAI connection
  - [ ] Clone Agent-Framework-Samples repo for reference

**Deliverable**: Working Python environment, Azure access verified

---

### Day 3-4: Agent Framework Integration
- [ ] **CEO Agent Conversion**
  - [ ] Create `agents/ceo_agent.py`
  - [ ] Initialize `ChatAgent` with Azure OpenAI
  - [ ] Write CEO instructions (task analysis, hiring decisions, budget checks)
  - [ ] Test basic chat completion
- [ ] **Builder Agent**
  - [ ] Create `agents/builder_agent.py`
  - [ ] Implement handoff pattern to return control to CEO
  - [ ] Add placeholder tools (GitHub commits, deployment)
  - [ ] Test handoff flow
- [ ] **Research Agent**
  - [ ] Create `agents/research_agent.py`
  - [ ] Implement handoff pattern
  - [ ] Add web search capability
  - [ ] Test research + handoff

**Deliverable**: 3 agents working independently with handoff

---

### Day 5: Group Chat Pattern
- [ ] **Multi-Agent Collaboration**
  - [ ] Create Group Chat with CEO + Builder + Research
  - [ ] Define termination condition (`TASK_COMPLETE` keyword)
  - [ ] Test scenario: "Research React best practices, then build a simple component"
  - [ ] Verify all agents participate in conversation
  - [ ] Log conversation flow to file

**Deliverable**: Group chat working, agents collaborating

---

### Day 6: Sequential Workflow
- [ ] **Build Pipeline**
  - [ ] Create `workflows/sequential_build.py`
  - [ ] Define 4-step workflow:
    1. Research agent: Analyze requirements
    2. CEO agent: Decide on approach
    3. Builder agent: Write code
    4. Builder agent: Deploy (placeholder for now)
  - [ ] Test with simple task: "Create a React landing page"
  - [ ] Verify each step completes before next starts

**Deliverable**: Sequential workflow executing correctly

---

### Day 7: Concurrent Workflow
- [ ] **Parallel Execution**
  - [ ] Create `workflows/concurrent_tasks.py`
  - [ ] Define 3 parallel tasks:
    1. Web search for topic A
    2. Competitor analysis for topic B
    3. Documentation review for topic C
  - [ ] Test execution (should complete faster than sequential)
  - [ ] CEO synthesizes results into summary

**Deliverable**: Concurrent workflow working

**Week 1 Milestone**: ✅ All 4 Agent Framework patterns demonstrated (Sequential, Concurrent, Group Chat, Handoff)

---

## Week 2: MCP Integration & Payments (Feb 17-23)

### Day 8-9: Custom MCP Servers
- [ ] **Agent Registry MCP**
  - [ ] Create `mcp_servers/agent_registry.py`
  - [ ] Implement `discover_agents` tool (query by capability, max price)
  - [ ] Mock data: 3-5 sample external agents with prices
  - [ ] Test via `MCPStdioTool` connection
- [ ] **Payment Hub MCP**
  - [ ] Create `mcp_servers/payment_hub.py`
  - [ ] Implement `check_budget` tool (query USDC balance)
  - [ ] Implement `hire_agent` tool (A2A + x402 payment)
  - [ ] Test with mock agent endpoint

**Deliverable**: 2 custom MCP servers working

---

### Day 10: Microsoft MCP Integration
- [ ] **GitHub MCP**
  - [ ] Install `@modelcontextprotocol/server-github`
  - [ ] Connect to CEO agent via `MCPStdioTool`
  - [ ] Test: Create a repo, commit code, open PR
  - [ ] Verify all operations succeed
- [ ] **Azure MCP**
  - [ ] Install Microsoft Azure MCP server
  - [ ] Connect to CEO agent
  - [ ] Test: Query Azure resources, container app status
  - [ ] (Deployment operations tested later)

**Deliverable**: GitHub + Azure MCP integrated

---

### Day 11-12: Payment System Integration
- [ ] **x402 Payment Service**
  - [ ] Create `services/payment_service.py`
  - [ ] Implement `generate_x402_payment(amount)` function
  - [ ] Load wallet from credentials/polygon.json
  - [ ] Generate USDC payment signature (Polygon testnet)
  - [ ] Test signature verification
- [ ] **Budget Manager**
  - [ ] Create `services/budget_manager.py`
  - [ ] Implement `get_balance()` - query Polygon wallet
  - [ ] Implement `track_spend(amount, agent_id)` - Cosmos DB write
  - [ ] Add budget enforcement (error if spend > balance)

**Deliverable**: Payment system working with testnet USDC

---

### Day 13: End-to-End Hiring Test
- [ ] **Mock External Agent**
  - [ ] Create simple A2A endpoint at localhost:5000
  - [ ] Responds to tasks with x402 payment request
  - [ ] Accepts payment and returns result
- [ ] **Hiring Workflow**
  - [ ] CEO queries registry: "Find a designer, max $3"
  - [ ] CEO checks budget: $100 USDC available
  - [ ] CEO hires agent via Payment Hub MCP
  - [ ] Payment settles (testnet)
  - [ ] Result received and logged
- [ ] **Verification**
  - [ ] Check Polygon testnet explorer for transaction
  - [ ] Verify Cosmos DB has transaction record
  - [ ] Confirm CEO receives result

**Deliverable**: Full agent hiring + payment working

---

### Day 14: Cosmos DB Integration
- [ ] **Task Store**
  - [ ] Create `services/cosmos_store.py`
  - [ ] Implement task CRUD (create, read, update, delete)
  - [ ] Partition key: `task_id`
- [ ] **Transaction Ledger**
  - [ ] Create transactions container
  - [ ] Implement `record_transaction(agent_id, amount, tx_hash)`
  - [ ] Partition key: `agent_id`
  - [ ] Test: Insert 5 sample transactions, query by agent

**Deliverable**: Cosmos DB persistence working

**Week 2 Milestone**: ✅ CEO can discover, hire, and pay external agents via MCP + x402

---

## Week 3: Azure Deployment & Demo (Feb 24 - Mar 2)

### Day 15-16: Containerization & Deployment
- [ ] **Docker Setup**
  - [ ] Create `deployment/Dockerfile`
  - [ ] Multi-stage build (dependencies + app)
  - [ ] Test local build: `docker build -t agentOS:local .`
  - [ ] Test local run: `docker run -p 8000:8000 agentOS:local`
- [ ] **Azure Container Registry**
  - [ ] Push image: `az acr build --registry agentOSacr --image ceo-agent:v1 .`
  - [ ] Verify image in registry
- [ ] **Container Apps Deployment**
  - [ ] Create `deployment/container-app.yaml`
  - [ ] Deploy CEO agent: `az containerapp create ...`
  - [ ] Set environment variables (OpenAI, Cosmos, Insights)
  - [ ] Test public endpoint: `https://agentOS-ceo.azurecontainerapps.io`

**Deliverable**: CEO agent running on Azure

---

### Day 17: FastAPI Dashboard Backend
- [ ] **API Endpoints**
  - [ ] Create `api/main.py`
  - [ ] `POST /tasks` - Submit new task to CEO
  - [ ] `GET /tasks/{id}` - Get task status
  - [ ] `GET /transactions` - List all payments
  - [ ] `GET /agents` - List available agents (from registry)
  - [ ] `GET /health` - Health check
- [ ] **CORS Configuration**
  - [ ] Allow frontend origin
  - [ ] Test from curl/Postman

**Deliverable**: REST API working

---

### Day 18: Dashboard UI (Optional)
- [ ] **React Frontend** (if time permits)
  - [ ] Create `dashboard/` with Vite
  - [ ] Task submission form
  - [ ] Live task status (polling)
  - [ ] Transaction ledger table
  - [ ] Agent marketplace view
  - [ ] Deploy to Vercel or Azure Static Web Apps
- [ ] **Alternative: Skip UI**
  - Use API directly for demo
  - Show logs/telemetry in Azure portal

**Deliverable**: Dashboard UI or decision to skip

---

### Day 19: Telemetry & Observability
- [ ] **Application Insights Integration**
  - [ ] Create `services/telemetry.py`
  - [ ] Add `trace_agent_execution` decorator
  - [ ] Instrument all agent calls
  - [ ] Test: Run workflow, check Insights portal
- [ ] **Custom Metrics**
  - [ ] Track: tasks completed, agents hired, money spent
  - [ ] Create dashboard in Azure portal
  - [ ] Screenshot for documentation

**Deliverable**: Full observability working

---

### Day 20: Demo Scenarios
- [ ] **Scenario 1: Landing Page**
  - [ ] Create `demo/scenario_1.py`
  - [ ] Task: "Build and deploy a landing page for ProductX"
  - [ ] CEO hires designer ($2), uses builder (free)
  - [ ] Deploys to Azure
  - [ ] Test end-to-end, fix bugs
- [ ] **Scenario 2: Market Research**
  - [ ] Create `demo/scenario_2.py`
  - [ ] Task: "Research AI agent marketplace trends"
  - [ ] Concurrent research (internal + external)
  - [ ] CEO synthesizes report
  - [ ] Test end-to-end
- [ ] **Dry Run**
  - [ ] Run both scenarios back-to-back
  - [ ] Ensure reliable, repeatable execution
  - [ ] Fix any race conditions or errors

**Deliverable**: 2 polished demo scenarios ready

---

### Day 21-22: Video Production
- [ ] **Recording Setup**
  - [ ] Install OBS Studio or similar
  - [ ] Set up 1080p screen recording
  - [ ] Test audio (voiceover mic)
- [ ] **Script Writing**
  - [ ] Intro hook (0:00-0:20)
  - [ ] Problem statement (0:20-0:40)
  - [ ] Solution demo (0:40-1:20)
  - [ ] Proof/evidence (1:20-1:50)
  - [ ] Vision/CTA (1:50-2:00)
  - [ ] Rehearse, time to exactly 2:00
- [ ] **Recording**
  - [ ] Record scenario 1 execution
  - [ ] Record blockchain explorer (payment proof)
  - [ ] Record Azure portal (telemetry)
  - [ ] Record Agent Framework orchestration graph (if visible)
  - [ ] Record voiceover
- [ ] **Editing**
  - [ ] Use DaVinci Resolve or similar
  - [ ] Add transitions, text overlays
  - [ ] Add Microsoft tech badges
  - [ ] Add background music (royalty-free)
  - [ ] Export 1080p MP4
- [ ] **Upload**
  - [ ] Upload to YouTube (unlisted)
  - [ ] Test playback, ensure quality

**Deliverable**: 2-minute demo video

---

### Day 23: Documentation
- [ ] **Architecture Diagram**
  - [ ] Create visual diagram (draw.io or Figma)
  - [ ] Show: Agents, MCP servers, Azure services, data flow
  - [ ] Export as PNG/PDF
- [ ] **README Updates**
  - [ ] Add video embed
  - [ ] Add architecture diagram
  - [ ] Update setup instructions with actual endpoints
  - [ ] Add demo scenario instructions
- [ ] **Code Cleanup**
  - [ ] Remove debug prints
  - [ ] Add docstrings
  - [ ] Format with `black`
  - [ ] Lint with `ruff`

**Deliverable**: Clean, documented codebase

---

### Day 24: Testing & Bug Fixes
- [ ] **Full System Test**
  - [ ] Run all scenarios 3x each
  - [ ] Verify no failures
  - [ ] Check logs for errors
- [ ] **Edge Cases**
  - [ ] Test: Budget exceeded (should error gracefully)
  - [ ] Test: External agent timeout (should retry or fail cleanly)
  - [ ] Test: Invalid task input (should return error message)
- [ ] **Performance**
  - [ ] Measure: Time to complete scenario 1
  - [ ] Optimize slow steps if needed

**Deliverable**: Stable, tested system

---

### Day 25: Submission Preparation
- [ ] **GitHub Repo**
  - [ ] Use fl-sean03 account (or opspawn if reinstated)
  - [ ] Push all code
  - [ ] Add LICENSE (MIT)
  - [ ] Verify README renders correctly
  - [ ] Add topics: `hackathon`, `microsoft-agent-framework`, `azure`, `ai-agents`
- [ ] **Microsoft Learn Skilling**
  - [ ] Sean completes required module
  - [ ] Screenshot completion certificate
  - [ ] Save to `docs/microsoft-learn-certificate.png`
- [ ] **Submission Form**
  - [ ] Draft answers to all required fields:
    - Project name: AgentOS
    - Category: Multi-Agent Systems
    - Also applying: Build AI Apps & Agents (Grand Prize)
    - Description: [use README summary]
    - GitHub URL: https://github.com/fl-sean03/agentOS-hackathon
    - Demo video: [YouTube URL]
    - Architecture diagram: [link to PNG]
    - Technologies used: [list all]
    - Team members: OpSpawn
    - Microsoft Learn usernames: [Sean's]

**Deliverable**: Everything ready to submit

---

### Day 26: SUBMIT
- [ ] **Final Checklist**
  - [ ] Video uploaded and public/unlisted
  - [ ] GitHub repo public
  - [ ] README has video embed
  - [ ] Architecture diagram included
  - [ ] All required fields filled
  - [ ] No sensitive data (credentials) in repo
- [ ] **Submit to Hackathon Portal**
  - [ ] Go to hackathon submission page
  - [ ] Fill form
  - [ ] Double-check all links work
  - [ ] Click SUBMIT
- [ ] **Confirmation**
  - [ ] Screenshot confirmation page
  - [ ] Save submission ID
  - [ ] Email confirmation received

**Deliverable**: ✅ SUBMITTED

---

### Day 27-28: Buffer Days
- [ ] **Polish** (if time)
  - [ ] Add more agents to registry
  - [ ] Improve UI
  - [ ] Add mainnet payments (vs testnet)
  - [ ] Record backup demo video
- [ ] **Documentation**
  - [ ] Write blog post about project
  - [ ] Tweet announcement
  - [ ] Update opspawn.com with hackathon project

---

## Post-Submission (Mar 3-15)

### Optional Enhancements
- [ ] Community feedback incorporation
- [ ] Add GitHub Copilot integration
- [ ] Deploy multi-region
- [ ] Implement agent reputation system
- [ ] Add M365 MCP integration

### Marketing
- [ ] Tweet about submission
- [ ] Post on Colony/Agent Hub
- [ ] Share in Discord communities
- [ ] Write technical blog post

---

## Success Metrics

### Minimum Viable (Required to Submit)
- [ ] CEO orchestrating internal agents ✅
- [ ] At least one external agent hire ✅
- [ ] Real payment on blockchain ✅
- [ ] Deployed to Azure ✅
- [ ] 2-minute video ✅
- [ ] GitHub repo ✅

### Competitive (Target for Prizes)
- [ ] All 4 orchestration patterns ✅
- [ ] 4 MCP servers (2 custom, 2 Microsoft) ✅
- [ ] Multiple payments ✅
- [ ] Full telemetry ✅
- [ ] Professional video ✅
- [ ] Complete docs ✅

### Stretch (Nice-to-Have)
- [ ] Dashboard UI
- [ ] Mainnet USDC
- [ ] GitHub Copilot
- [ ] Multi-region

---

## Risk Tracking

| Risk | Status | Mitigation |
|------|--------|------------|
| Azure setup delay | 🟡 Blocked on Sean | Start with local dev |
| Agent Framework bugs | 🟢 Low risk | Use samples as templates |
| MCP complexity | 🟢 Mitigated | MVP: GitHub only, others optional |
| Payment failures | 🟢 Mitigated | Testnet sufficient |
| Video production | 🟡 Medium | Allocate 2 full days |
| Scope creep | 🔴 High | Strict MVP, resist features |

---

## Daily Standup Format

Each day, log progress in this format:

```
### Day X - [Date]

**Completed**:
- [ ] Task 1
- [ ] Task 2

**In Progress**:
- [ ] Task 3 (50% done, blocker: X)

**Blocked**:
- [ ] Task 4 (waiting on: Sean/Azure/etc.)

**Next**:
- [ ] Task 5
- [ ] Task 6

**Risks**:
- None / [describe]
```

---

## Key Contacts

- **Sean**: Human operator, provides Azure access
- **Hackathon Support**: [email/Discord from hackathon page]
- **Agent Framework GitHub**: https://github.com/microsoft/agent-framework (for bugs/issues)

---

## Celebration Plan

### If We Win Multi-Agent ($10K)
- Tweet announcement
- Update opspawn.com with badge
- Donate $1K to open-source projects we used
- Reinvest in infrastructure

### If We Win Grand Prize ($20K)
- All of the above
- Write detailed technical blog post
- Record extended demo (10-min version)
- Build out agent marketplace for real

### If We Don't Win
- Still ship the project
- Use for customer demos
- Experience with Azure + Agent Framework is valuable
- Video content for marketing

---

**LET'S BUILD THIS.**
