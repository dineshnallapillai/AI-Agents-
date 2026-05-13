# AI Agents: From Chatbots to Autonomous Systems

## 1. The Shift 

### From Chatbots to Agents — What Changed?

| Generation | Capability | Example |
|------------|-----------|---------|
| **Chatbot** | Responds to one question at a time | "What's the weather?" → "It's 25°C" |
| **Copilot** | Assists within a workflow | Suggests code as you type |
| **Agent** | Autonomously plans and executes multi-step tasks | "Book me the cheapest flight to London next Friday" → searches, compares, books |

### Key Insight

> An AI Agent is not just a smarter chatbot — it's an LLM with **goals**, **tools**, and the ability to **take actions** in the real world.

---

## 2. How Agents Think 

### The Agent Loop

```
┌─────────────────────────────────────┐
│                                     │
│   Goal → Plan → Act → Observe      │
│     ↑                       │       │
│     └───────────────────────┘       │
│         (repeat until done)         │
│                                     │
└─────────────────────────────────────┘
```

### The Three Pillars

#### 1. Reasoning (The Brain)
- Breaks complex tasks into smaller steps
- Decides what to do next based on observations
- Adjusts the plan when something fails

#### 2. Tools (The Hands)
- Web search, code execution, APIs, databases
- File reading/writing, email, calendar
- Any system the agent can call

#### 3. Memory (The Context)
- **Short-term**: Current conversation and task state
- **Long-term**: Learned preferences, past interactions
- **Episodic**: What worked before in similar situations

### Analogy for Non-Technical Audience

> Think of an agent like a **new employee** who:
> - Gets a task from their manager (the user)
> - Has access to company tools (email, CRM, databases)
> - Breaks the task into steps, does each one, checks their work
> - Asks for help when they're stuck or unsure

---

## 3. Patterns That Work 

### Pattern 1: Single Agent + Tools

```
User → [Agent] → Tool A (Search)
                → Tool B (Calculator)
                → Tool C (Code Runner)
             → Final Answer
```

**Use case**: Coding assistants, research agents, customer support

**Example**: "Analyze last quarter's sales data and create a summary report"
- Agent reads the CSV → runs calculations → generates charts → writes report

---

### Pattern 2: Multi-Agent Collaboration

```
User → [Orchestrator Agent]
            ├── [Research Agent] → gathers info
            ├── [Analyst Agent] → processes data
            └── [Writer Agent] → produces output
```

**Use case**: Complex workflows requiring different expertise

**Example**: "Write a market analysis for entering the EU market"
- Research agent gathers regulations, market data
- Analyst agent identifies opportunities and risks
- Writer agent produces the final report

---

### Pattern 3: Human-in-the-Loop

```
User → [Agent] → works autonomously
                → hits uncertainty threshold
                → asks user for guidance
                → continues with new info
```

**Use case**: High-stakes decisions, ambiguous requirements

**Example**: "Refactor the authentication module"
- Agent proposes a plan → user approves/modifies → agent executes → user reviews

---

### Comparison Table

| Pattern | Autonomy | Complexity | Best For |
|---------|----------|-----------|----------|
| Single Agent | Medium | Low | Well-defined tasks |
| Multi-Agent | High | High | Complex workflows |
| Human-in-Loop | Low | Variable | High-stakes decisions |

---

## 4. Live Demo 

### Demo Options

#### Option A: Coding Agent (Claude Code)
- Give the agent a task: "Add input validation to this API endpoint"
- Show the reasoning trace as it plans and executes
- Highlight: tool usage, iterative refinement, self-correction

#### Option B: Research Agent
- Ask: "Compare the top 3 cloud providers for a startup with 10 engineers"
- Show: how it searches, synthesizes, and structures findings

#### Option C: Multi-Agent Workflow
- Task: "Review this PR for security issues and suggest fixes"
- Show: agents collaborating — one reads code, one checks against OWASP, one writes suggestions

### What to Highlight During Demo
- The agent's "thinking" / reasoning trace
- When it chooses which tool to use and why
- How it handles errors or unexpected results
- The iterative nature — plan, act, observe, adjust

---

## 5. Where It's Heading 

### Near-Term (2025–2026)

| Trend | Impact |
|-------|--------|
| **Agents in enterprise workflows** | Automating multi-step business processes end-to-end |
| **Agent-to-agent protocols** | Standardized communication (MCP, A2A) |
| **Specialized agents** | Domain-specific agents (legal, medical, financial) |
| **Computer use** | Agents that navigate UIs like humans |

### Medium-Term (2026–2028)

- **Agent marketplaces**: Hire pre-built agents for specific tasks
- **Persistent agents**: Always-on agents monitoring and acting proactively
- **Self-improving agents**: Agents that learn from their successes and failures
- **Agent teams as a service**: Deploy a "team" of agents instead of hiring for routine work

### The Ecosystem is Forming

```
┌──────────────────────────────────────────────┐
│          Agent Ecosystem                      │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Tools &  │  │ Agent    │  │ Safety & │  │
│  │ APIs     │  │ Frame-   │  │ Guard-   │  │
│  │ (MCP)    │  │ works    │  │ rails    │  │
│  └──────────┘  └──────────┘  └──────────┘  │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Memory & │  │ Eval &   │  │ Human    │  │
│  │ State    │  │ Monitor  │  │ Oversight│  │
│  └──────────┘  └──────────┘  └──────────┘  │
│                                              │
└──────────────────────────────────────────────┘
```

---

## 6. When NOT to Use Agents 

### Don't Use an Agent When...

| Situation | Better Alternative |
|-----------|--------------------|
| Task has fixed, predictable steps | Simple automation / script |
| Zero tolerance for error | Rule-based system with human review |
| Response time must be < 1 second | Pre-computed answers / cache |
| Task requires no reasoning | Traditional API call |
| A good UI solves the problem | Build the UI instead |

### The Decision Framework

```
Is the task multi-step?
  └── No → Use a simple API/script
  └── Yes → Does it require reasoning?
              └── No → Use a workflow engine
              └── Yes → Does it need real-time response?
                          └── Yes → Use copilot/assisted mode
                          └── No → Agent is a good fit ✓
```

### Risks to Acknowledge

- **Hallucination propagation**: One wrong step compounds through the chain
- **Cost**: Agent loops can burn through API calls quickly
- **Unpredictability**: Same input ≠ same output every time
- **Security**: Agents with tool access can cause real-world damage if unsupervised

---

## Key Takeaways

1. **Agents = LLM + Tools + Loop** — They plan, act, and iterate autonomously
2. **Pattern matters** — Match the architecture to the problem complexity
3. **Human oversight is a feature, not a limitation** — The best agents know when to ask
4. **We're early** — The ecosystem is forming now; understanding agents is a strategic advantage
5. **Not everything needs an agent** — Use the right tool for the right job

---

## Resources for Further Learning

| Resource | Type | Link |
|----------|------|------|
| Anthropic Agent Documentation | Docs | anthropic.com/docs |
| LangGraph | Framework | langchain.com |
| CrewAI | Multi-Agent Framework | crewai.com |
| AutoGen (Microsoft) | Research Framework | github.com/microsoft/autogen |
| MCP (Model Context Protocol) | Standard | modelcontextprotocol.io |

---

*Session prepared: May 2026*
