# AgentOS Implementation Guide
## Technical Setup & Code Patterns

---

## Phase 1: Environment Setup

### Prerequisites
1. **Azure Subscription** (Sean must set up)
   - Resource group: `agentOS-hackathon`
   - Region: East US (lower latency for demos)
   - Services: Container Apps, Cosmos DB, OpenAI, Storage, Application Insights

2. **Python Environment**
   ```bash
   cd /home/agent/projects/ms-agent-framework-hackathon
   python3.12 -m venv venv
   source venv/bin/activate
   pip install agent-framework --pre
   pip install azure-ai-agents azure-identity azure-cosmos
   pip install uvicorn fastapi  # for REST endpoints
   ```

3. **Azure CLI & Auth**
   ```bash
   curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
   az login  # Sean must do this
   az account set --subscription <subscription-id>
   ```

---

## Phase 2: Agent Framework Setup

### Project Structure
```
ms-agent-framework-hackathon/
├── agents/
│   ├── ceo_agent.py           # Main orchestrator
│   ├── builder_agent.py       # Internal code builder
│   ├── research_agent.py      # Internal researcher
│   └── registry_agent.py      # External agent discovery
├── mcp_servers/
│   ├── agent_registry.py      # Custom MCP: list available agents
│   └── payment_hub.py         # Custom MCP: handle x402 payments
├── workflows/
│   ├── sequential_build.py    # Research → Build → Deploy
│   ├── concurrent_tasks.py    # Parallel execution
│   └── hiring_workflow.py     # Discover → Evaluate → Hire
├── services/
│   ├── cosmos_store.py        # Task/payment persistence
│   ├── telemetry.py           # Application Insights
│   └── budget_manager.py      # USDC balance tracking
├── api/
│   └── main.py                # FastAPI endpoints for dashboard
├── dashboard/                  # React UI (if time)
├── deployment/
│   ├── Dockerfile
│   ├── container-app.yaml
│   └── cosmos-setup.sh
└── demo/
    ├── scenario_1.py          # Landing page task
    ├── scenario_2.py          # Multi-agent research
    └── record_demo.sh         # Video capture script
```

### CEO Agent (Group Chat Pattern)

```python
# agents/ceo_agent.py
from agent_framework import ChatAgent
from agent_framework.providers.azure_openai import AzureOpenAIChatClient
from agent_framework.workflows import GroupChat
from azure.identity import DefaultAzureCredential

# Initialize Azure OpenAI
client = AzureOpenAIChatClient(
    endpoint="https://<resource>.openai.azure.com",
    api_key=None,  # Uses DefaultAzureCredential
    deployment="gpt-4",
    credential=DefaultAzureCredential()
)

# CEO Agent Instructions
CEO_INSTRUCTIONS = """
You are the CEO Agent of AgentOS. Your job:
1. Receive tasks from users or webhooks
2. Break down complex tasks into subtasks
3. Analyze which agents (internal or external) can handle each subtask
4. Check budget and make hiring decisions
5. Orchestrate agent collaboration using Microsoft Agent Framework
6. Synthesize results and report back

When evaluating agents:
- Internal agents (Builder, Research) are free
- External agents cost $1-$10 USDC depending on complexity
- Only hire external if task requires specialized skills not available internally
- Always check budget before hiring

You have access to these tools:
- discover_agents: Query agent registry for available agents
- check_budget: Get current USDC balance
- hire_agent: Send task to external agent and pay via x402
- assign_internal: Delegate to Builder or Research agent
"""

# Initialize CEO Agent
ceo_agent = ChatAgent(
    chat_client=client,
    instructions=CEO_INSTRUCTIONS,
    name="CEO"
)

# Group Chat Setup
async def orchestrate_task(task_description: str):
    """Main orchestration entry point"""
    from agents.builder_agent import builder_agent
    from agents.research_agent import research_agent

    # Create group chat with all internal agents
    group = GroupChat(
        agents=[ceo_agent, builder_agent, research_agent],
        max_turns=20,
        termination_condition=lambda msg: "TASK_COMPLETE" in msg.content
    )

    # Start the conversation
    result = await group.run(task_description)
    return result
```

### Builder Agent (Handoff Pattern)

```python
# agents/builder_agent.py
from agent_framework import ChatAgent, handoff
from agent_framework.providers.azure_openai import AzureOpenAIChatClient
from mcp_servers.github_mcp import github_tools

BUILDER_INSTRUCTIONS = """
You are the Builder Agent. You write code, create repositories, and deploy applications.

You have access to:
- GitHub (create repos, commit code, create PRs)
- Azure Container Apps (deploy services)
- Docker (containerize apps)

When you complete a task:
1. Commit code to GitHub
2. Deploy to Azure if requested
3. Return a summary with URLs
4. Use HANDOFF to return control to CEO
"""

builder_agent = ChatAgent(
    chat_client=client,
    instructions=BUILDER_INSTRUCTIONS,
    name="Builder",
    tools=[
        *github_tools,  # From GitHub MCP
        handoff(ceo_agent, "Return control to CEO after completing task")
    ]
)
```

### Research Agent (Handoff Pattern)

```python
# agents/research_agent.py
from agent_framework import ChatAgent, handoff

RESEARCH_INSTRUCTIONS = """
You are the Research Agent. You gather information, analyze data, and provide insights.

You can:
- Search the web (Bing API)
- Read documentation
- Analyze competitors
- Summarize findings

When done, use HANDOFF to return findings to CEO.
"""

research_agent = ChatAgent(
    chat_client=client,
    instructions=RESEARCH_INSTRUCTIONS,
    name="Research",
    tools=[
        # Bing search tool, web scraping, etc.
        handoff(ceo_agent, "Return research results to CEO")
    ]
)
```

---

## Phase 3: MCP Integration

### Custom MCP Server: Agent Registry

```python
# mcp_servers/agent_registry.py
from mcp.server.mcp import McpServer
from mcp.server.stdio import StdioServerTransport

server = McpServer("agent-registry")

@server.tool(
    name="discover_agents",
    description="Find available agents by capability",
    parameters={
        "type": "object",
        "properties": {
            "capability": {
                "type": "string",
                "description": "Required capability (e.g., 'design', 'data-analysis', 'video-editing')"
            },
            "max_price": {
                "type": "number",
                "description": "Maximum price willing to pay in USDC"
            }
        },
        "required": ["capability"]
    }
)
async def discover_agents(capability: str, max_price: float = 10.0):
    """Query agent marketplace for matching agents"""
    # In MVP: return mock agents
    # In full version: query Agent Hub, Colony, Nevermined

    agents = [
        {
            "id": "designer_001",
            "name": "DesignBot",
            "capability": "design",
            "price_usd": 2.0,
            "rating": 4.8,
            "endpoint": "https://designbot.example.com/a2a",
            "mcp_endpoint": "wss://designbot.example.com/mcp"
        },
        {
            "id": "analyst_042",
            "name": "DataWizard",
            "capability": "data-analysis",
            "price_usd": 5.0,
            "rating": 4.9,
            "endpoint": "https://datawizard.example.com/a2a"
        }
    ]

    # Filter by capability and price
    matches = [
        a for a in agents
        if capability.lower() in a["capability"].lower()
        and a["price_usd"] <= max_price
    ]

    return {
        "content": [
            {
                "type": "text",
                "text": f"Found {len(matches)} agents:\n" +
                        "\n".join([f"- {a['name']}: ${a['price_usd']} ({a['rating']}★)" for a in matches])
            }
        ]
    }

@server.tool(
    name="check_budget",
    description="Get current USDC balance",
    parameters={"type": "object", "properties": {}}
)
async def check_budget():
    """Return current wallet balance"""
    from services.budget_manager import get_balance
    balance = await get_balance()
    return {
        "content": [{
            "type": "text",
            "text": f"Current balance: ${balance:.2f} USDC"
        }]
    }

if __name__ == "__main__":
    import asyncio
    async def main():
        async with StdioServerTransport() as transport:
            await server.run(transport)
    asyncio.run(main())
```

### Custom MCP Server: Payment Hub

```python
# mcp_servers/payment_hub.py
from mcp.server.mcp import McpServer
import aiohttp
import json

server = McpServer("payment-hub")

@server.tool(
    name="hire_agent",
    description="Hire an external agent and pay via x402",
    parameters={
        "type": "object",
        "properties": {
            "agent_id": {"type": "string"},
            "task": {"type": "string"},
            "max_price": {"type": "number"}
        },
        "required": ["agent_id", "task", "max_price"]
    }
)
async def hire_agent(agent_id: str, task: str, max_price: float):
    """
    1. Send A2A message with task
    2. Agent responds with x402 payment request
    3. Generate USDC payment signature
    4. Re-send message with payment proof
    5. Receive result
    """
    # Load agent details from registry
    from services.cosmos_store import get_agent_by_id
    agent = await get_agent_by_id(agent_id)

    if not agent:
        return {"content": [{"type": "text", "text": f"Agent {agent_id} not found"}]}

    # Step 1: Send task (A2A protocol)
    async with aiohttp.ClientSession() as session:
        # Initial request
        payload = {
            "method": "message/send",
            "params": {
                "message": {
                    "parts": [{"kind": "text", "text": task}],
                    "metadata": {"task_type": "one_shot"}
                }
            }
        }

        async with session.post(agent["endpoint"], json=payload) as resp:
            result = await resp.json()

        # Check for payment request
        if result.get("status") == "input-required":
            accepts = result["params"]["metadata"].get("x402.accepts", [])
            price = float(accepts[0].split("$")[1]) if accepts else max_price

            if price > max_price:
                return {"content": [{"type": "text", "text": f"Agent price ${price} exceeds budget ${max_price}"}]}

            # Step 2: Generate payment (x402 protocol)
            from services.payment_service import generate_x402_payment
            payment = await generate_x402_payment(amount=price)

            # Step 3: Resend with payment
            payload["params"]["message"]["metadata"]["x402.payment.payload"] = payment
            async with session.post(agent["endpoint"], json=payload) as resp2:
                final_result = await resp2.json()

            # Record transaction
            from services.cosmos_store import record_transaction
            await record_transaction(
                agent_id=agent_id,
                task=task,
                amount=price,
                tx_hash=payment["signature"]
            )

            return {
                "content": [{
                    "type": "text",
                    "text": f"Task completed by {agent['name']}. Paid ${price} USDC.\n\n" +
                            f"Result: {final_result['params']['message']['parts'][0]['text']}"
                }]
            }

    return {"content": [{"type": "text", "text": "Unknown error"}]}
```

### Connecting MCP Servers to CEO Agent

```python
# agents/ceo_agent.py (updated)
from agent_framework.tools import MCPStdioTool

async def create_ceo_agent():
    """Create CEO agent with MCP tools"""

    # Connect to custom MCP servers
    async with (
        MCPStdioTool(
            name="agent-registry",
            command="python",
            args=["mcp_servers/agent_registry.py"]
        ) as registry_mcp,
        MCPStdioTool(
            name="payment-hub",
            command="python",
            args=["mcp_servers/payment_hub.py"]
        ) as payment_mcp,
        MCPStdioTool(
            name="github",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"]
        ) as github_mcp,
        MCPStdioTool(
            name="azure",
            command="python",
            args=["-m", "mcp_azure"]  # Microsoft's Azure MCP
        ) as azure_mcp
    ):
        ceo_agent = ChatAgent(
            chat_client=client,
            instructions=CEO_INSTRUCTIONS,
            tools=[registry_mcp, payment_mcp, github_mcp, azure_mcp]
        )

        return ceo_agent
```

---

## Phase 4: Workflows

### Sequential Workflow: Build Pipeline

```python
# workflows/sequential_build.py
from agent_framework.workflows import Sequential

async def build_landing_page(product_name: str, description: str):
    """
    Sequential workflow:
    1. Research competitors
    2. Create design (hire external designer)
    3. Build code (internal builder)
    4. Deploy to Azure
    """

    workflow = Sequential(
        steps=[
            {
                "agent": research_agent,
                "task": f"Research top 5 landing pages for {product_name}. Extract design patterns."
            },
            {
                "agent": ceo_agent,
                "task": "Based on research, hire a designer for mockup. Budget: $3 USDC."
            },
            {
                "agent": builder_agent,
                "task": "Implement landing page using design mockup. Use React + Tailwind."
            },
            {
                "agent": builder_agent,
                "task": "Deploy to Azure Container Apps and return live URL."
            }
        ]
    )

    result = await workflow.run()
    return result
```

### Concurrent Workflow: Parallel Research

```python
# workflows/concurrent_tasks.py
from agent_framework.workflows import Concurrent

async def comprehensive_research(topic: str):
    """
    Run multiple research tasks in parallel
    """

    workflow = Concurrent(
        tasks=[
            {
                "agent": research_agent,
                "task": f"Web search: latest trends in {topic}"
            },
            {
                "agent": research_agent,
                "task": f"Analyze top 3 competitors in {topic}"
            },
            {
                "agent": ceo_agent,
                "task": f"Hire market analyst to provide industry report on {topic}. Budget: $5."
            }
        ]
    )

    results = await workflow.run()

    # CEO synthesizes all results
    synthesis = await ceo_agent.run(
        f"Synthesize these research findings into executive summary:\n\n{results}"
    )

    return synthesis
```

---

## Phase 5: Azure Deployment

### Cosmos DB Setup

```python
# services/cosmos_store.py
from azure.cosmos import CosmosClient, PartitionKey
from azure.identity import DefaultAzureCredential
import os

class TaskStore:
    def __init__(self):
        endpoint = os.getenv("COSMOS_ENDPOINT")
        credential = DefaultAzureCredential()

        self.client = CosmosClient(endpoint, credential=credential)
        self.database = self.client.create_database_if_not_exists("agentOS")

        # Containers
        self.tasks = self.database.create_container_if_not_exists(
            id="tasks",
            partition_key=PartitionKey(path="/task_id")
        )

        self.transactions = self.database.create_container_if_not_exists(
            id="transactions",
            partition_key=PartitionKey(path="/agent_id")
        )

    async def create_task(self, task_id: str, description: str, assigned_to: str):
        """Store new task"""
        self.tasks.create_item({
            "id": task_id,
            "task_id": task_id,
            "description": description,
            "assigned_to": assigned_to,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat()
        })

    async def record_transaction(self, agent_id: str, task: str, amount: float, tx_hash: str):
        """Record payment transaction"""
        self.transactions.create_item({
            "id": tx_hash,
            "agent_id": agent_id,
            "task": task,
            "amount": amount,
            "tx_hash": tx_hash,
            "timestamp": datetime.utcnow().isoformat()
        })
```

### Application Insights

```python
# services/telemetry.py
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace
import os

# Configure Azure Monitor
configure_azure_monitor(
    connection_string=os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
)

tracer = trace.get_tracer(__name__)

def trace_agent_execution(agent_name: str, task: str):
    """Decorator to trace agent execution"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(f"{agent_name}.execute") as span:
                span.set_attribute("agent.name", agent_name)
                span.set_attribute("task.description", task)

                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("status", "error")
                    span.set_attribute("error.message", str(e))
                    raise
        return wrapper
    return decorator
```

### Dockerfile

```dockerfile
# deployment/Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY agents/ ./agents/
COPY mcp_servers/ ./mcp_servers/
COPY workflows/ ./workflows/
COPY services/ ./services/
COPY api/ ./api/

# Expose port
EXPOSE 8000

# Run FastAPI server
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Azure Container App Deployment

```yaml
# deployment/container-app.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agentOS-ceo
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: ceo-agent
        image: agentOSacr.azurecr.io/ceo-agent:latest
        env:
        - name: AZURE_OPENAI_ENDPOINT
          value: "https://<resource>.openai.azure.com"
        - name: COSMOS_ENDPOINT
          value: "https://<cosmos>.documents.azure.com"
        - name: APPLICATIONINSIGHTS_CONNECTION_STRING
          valueFrom:
            secretKeyRef:
              name: app-insights
              key: connection-string
        resources:
          requests:
            memory: "2Gi"
            cpu: "1"
```

---

## Phase 6: Demo Scenarios

### Scenario 1: Landing Page Creation

```python
# demo/scenario_1.py
"""
Demo: User requests landing page, CEO hires designer, builder codes, deploys to Azure
"""

async def demo_landing_page():
    from agents.ceo_agent import create_ceo_agent

    ceo = await create_ceo_agent()

    task = """
    Create a landing page for our new product "AgentOS" - an operating system for AI agents.

    Requirements:
    - Modern design with hero section
    - Feature highlights (multi-agent, payments, Azure-native)
    - Call-to-action button
    - Deploy to Azure Container Apps

    Budget: $10 USDC (can hire external designer if needed)
    """

    print("🎬 Starting demo: Landing Page Creation")
    print(f"📋 Task: {task}")
    print("\n" + "="*60 + "\n")

    # Execute via CEO
    result = await ceo.run(task)

    print("\n" + "="*60)
    print("✅ Demo complete!")
    print(f"📊 Result: {result}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(demo_landing_page())
```

### Scenario 2: Multi-Agent Research

```python
# demo/scenario_2.py
"""
Demo: Comprehensive market research using internal + external agents
"""

async def demo_research():
    from workflows.concurrent_tasks import comprehensive_research

    topic = "AI agent marketplaces and autonomous agent economics"

    print("🎬 Starting demo: Multi-Agent Research")
    print(f"📋 Topic: {topic}")
    print("\n" + "="*60 + "\n")

    result = await comprehensive_research(topic)

    print("\n" + "="*60)
    print("✅ Research complete!")
    print(f"📊 Executive Summary:\n{result}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(demo_research())
```

---

## Key Implementation Notes

### Authentication
- Use `DefaultAzureCredential()` everywhere (managed identity in Azure, local dev uses `az login`)
- Never hardcode API keys

### Error Handling
- Wrap all agent calls in try/except with telemetry
- If external agent fails, fallback to internal or skip
- Log all errors to Application Insights

### Budget Management
- Check balance before every hire
- Hard limit: never spend more than $50 in demo
- Track all transactions in Cosmos DB

### MCP Best Practices
- Keep MCP servers simple (single responsibility)
- Use stdio transport for local dev, WebSocket for production
- Always return `{"content": [{"type": "text", "text": "..."}]}` format

### Agent Framework Patterns
- **Sequential**: When order matters (build pipeline)
- **Concurrent**: When tasks are independent (research)
- **Group Chat**: When agents need to discuss (planning)
- **Handoff**: When specialized agent finishes sub-task

---

## Testing Checklist

Before demo recording:

- [ ] CEO agent can discover agents via MCP
- [ ] CEO can check budget
- [ ] CEO can orchestrate internal agents (Builder, Research)
- [ ] CEO can hire external agent and payment settles
- [ ] Sequential workflow completes end-to-end
- [ ] Concurrent workflow runs tasks in parallel
- [ ] All transactions logged to Cosmos DB
- [ ] Telemetry visible in Application Insights
- [ ] Deployed to Azure Container Apps
- [ ] Public endpoint working (https://agentOS.opspawn.com)

---

## Demo Recording Script

```bash
# demo/record_demo.sh

#!/bin/bash
# Record 2-minute demo video

echo "Starting AgentOS Demo Recording"
echo "================================"

# Terminal 1: Start CEO agent
python demo/scenario_1.py &
CEO_PID=$!

# Terminal 2: Monitor telemetry
az monitor app-insights query \
  --app agentOS \
  --analytics-query "traces | where timestamp > ago(5m)" \
  --output table &
MONITOR_PID=$!

# Terminal 3: Watch Cosmos DB
while true; do
  echo "--- Transactions ---"
  # Query Cosmos for recent transactions
  sleep 5
done &
COSMOS_PID=$!

# Let demo run
sleep 120  # 2 minutes

# Cleanup
kill $CEO_PID $MONITOR_PID $COSMOS_PID
echo "Demo recording complete!"
```

---

## Next Steps After Setup

1. **Week 1**: Get CEO orchestrating Builder/Research via Agent Framework
2. **Week 2**: Add MCP servers, implement one hiring workflow with real payment
3. **Week 3**: Deploy to Azure, create dashboard, record demo
4. **Submit**: GitHub repo (fl-sean03 account), video (YouTube), architecture diagram

**Goal**: Working end-to-end demo by Feb 24, polish by Mar 1, submit by Mar 2.
