# AI Agents: Comprehensive Session Guide

---

## Section 1: Core Concepts

---

### What are AI Agents vs. Plain LLMs vs. Chatbots

#### Definitions

| | Chatbot | LLM | AI Agent |
|--|---------|-----|----------|
| **What it is** | Rule-based or scripted responder | Large Language Model that generates text | LLM + Tools + Autonomy + Goals |
| **Memory** | None or session-only | Context window only | Short-term + Long-term memory |
| **Actions** | Pre-defined responses | Text generation | Can execute real-world actions |
| **Planning** | None | Limited reasoning | Multi-step planning and execution |
| **Autonomy** | Zero | Low | High |

#### The Evolution Timeline

```
Rule-Based Chatbots (2010s)
    │
    ▼
LLMs as Conversational AI (2022-2023)
    │
    ▼
LLMs with Tool Use (2023-2024)
    │
    ▼
Autonomous AI Agents (2024-2026)
    │
    ▼
Multi-Agent Systems (2025+)
```

#### Key Distinction

- **LLM**: "Here's what I think the answer is"
- **Agent**: "Let me figure this out — I'll search, calculate, verify, and give you a confirmed answer"

#### Example: "What's the stock price of Tesla?"

| System | Response |
|--------|----------|
| **Chatbot** | "I don't have real-time data. Please check a financial website." |
| **LLM** | "As of my last training data, Tesla was trading around $X..." (possibly outdated) |
| **Agent** | Calls stock API → gets real-time price → "Tesla is currently trading at $247.32, up 2.3% today." |

---

### The Agent Loop: Perceive → Reason → Act → Observe

#### The Fundamental Cycle

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│    ┌──────────┐    ┌──────────┐    ┌─────┐    ┌─────────┐ │
│    │ PERCEIVE │───▶│  REASON  │───▶│ ACT │───▶│ OBSERVE │ │
│    └──────────┘    └──────────┘    └─────┘    └─────────┘ │
│         ▲                                          │       │
│         └──────────────────────────────────────────┘       │
│                    (loop until goal met)                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Each Phase Explained

**1. Perceive**
- Receive input (user request, environment state, tool output)
- Parse and understand what's being asked
- Identify constraints and requirements

**2. Reason**
- Break the problem into sub-tasks
- Decide what information is needed
- Choose which tool or action to use next
- Evaluate if the current approach is working

**3. Act**
- Execute the chosen action (call a tool, write code, send a request)
- Actions have real effects on the environment

**4. Observe**
- Read the result of the action
- Determine if the result is satisfactory
- Check for errors or unexpected outcomes
- Decide: loop again or return final answer

#### Trace Example

```
User: "Find the most cited paper on transformer architectures and summarize it"

[PERCEIVE] User wants: most cited transformer paper + summary
[REASON]   I need to: 1) Search for papers 2) Find citation counts 3) Read top paper 4) Summarize
[ACT]      Call: academic_search("transformer architecture", sort_by="citations")
[OBSERVE]  Got results: "Attention Is All You Need" — 100,000+ citations

[REASON]   Found the paper. Now I need to read and summarize it.
[ACT]      Call: fetch_paper("Attention Is All You Need", 2017)
[OBSERVE]  Got full text of the paper.

[REASON]   I have the content. Now I can summarize.
[ACT]      Generate summary highlighting key contributions.
[OBSERVE]  Summary complete. Goal achieved.

→ Return final answer to user.
```

---

### Tool Use and Function Calling

#### What Are Tools?

Tools are external capabilities that extend what an LLM can do beyond text generation.

```
┌─────────────────────────────────────────────┐
│              AI Agent                        │
│                                             │
│   ┌──────────┐    ┌─────────────────────┐  │
│   │   LLM    │───▶│   Tool Interface    │  │
│   │  (Brain) │    │                     │  │
│   └──────────┘    │  ┌───────────────┐  │  │
│                    │  │ Web Search    │  │  │
│                    │  │ Code Runner   │  │  │
│                    │  │ Database      │  │  │
│                    │  │ File System   │  │  │
│                    │  │ APIs          │  │  │
│                    │  │ Calculator    │  │  │
│                    │  └───────────────┘  │  │
│                    └─────────────────────┘  │
│                                             │
└─────────────────────────────────────────────┘
```

#### How Function Calling Works

**Step 1**: Define available tools with schemas

```json
{
  "name": "get_weather",
  "description": "Get current weather for a location",
  "parameters": {
    "type": "object",
    "properties": {
      "location": { "type": "string", "description": "City name" },
      "unit": { "type": "string", "enum": ["celsius", "fahrenheit"] }
    },
    "required": ["location"]
  }
}
```

**Step 2**: LLM decides when and how to call tools

```
User: "Do I need an umbrella in London today?"

LLM thinks: I need current weather data → I'll call get_weather

Tool call: get_weather(location="London", unit="celsius")
Result: { "condition": "rainy", "temp": 14, "precipitation": 85% }

LLM: "Yes! London has an 85% chance of rain today at 14°C. Definitely bring an umbrella."
```

**Step 3**: Results flow back into the agent's reasoning

#### Categories of Tools

| Category | Examples | Use Case |
|----------|----------|----------|
| **Information** | Web search, Wikipedia, databases | Gathering facts |
| **Computation** | Calculator, code interpreter, SQL | Processing data |
| **Communication** | Email, Slack, SMS | Interacting with people |
| **File Operations** | Read, write, edit files | Managing documents |
| **System** | Shell commands, API calls | Infrastructure tasks |
| **Specialized** | Image generation, translation | Domain-specific work |

---

## Section 2: Architecture Patterns

---

### Single-Agent vs. Multi-Agent Systems

#### Single-Agent Architecture

```
┌─────────────────────────────────────┐
│           Single Agent              │
│                                     │
│   User ──▶ [Agent + Tools] ──▶ Output │
│                                     │
│   - One LLM handles everything     │
│   - All tools available to one agent│
│   - Simpler to build and debug      │
│                                     │
└─────────────────────────────────────┘
```

**Pros:**
- Simple to implement and debug
- Lower latency (no inter-agent communication)
- Easier to maintain context
- Lower cost

**Cons:**
- Context window limits
- Jack of all trades, master of none
- Single point of failure
- Hard to scale for complex tasks

#### Multi-Agent Architecture

```
┌───────────────────────────────────────────────────┐
│              Multi-Agent System                    │
│                                                   │
│   User ──▶ [Orchestrator]                         │
│                 │                                  │
│        ┌───────┼───────┐                          │
│        ▼       ▼       ▼                          │
│   [Agent A] [Agent B] [Agent C]                   │
│   Research   Analysis  Writing                    │
│        │       │       │                          │
│        └───────┼───────┘                          │
│                ▼                                   │
│            [Final Output]                         │
│                                                   │
└───────────────────────────────────────────────────┘
```

**Pros:**
- Each agent can specialize
- Parallel execution possible
- Better for complex, multi-domain tasks
- Scales with complexity

**Cons:**
- Harder to debug
- Communication overhead
- Higher cost (multiple LLM calls)
- Coordination challenges

#### When to Choose What

| Scenario | Recommendation |
|----------|---------------|
| Simple Q&A with tools | Single agent |
| Code generation + testing | Single agent |
| Full software project | Multi-agent |
| Research + analysis + writing | Multi-agent |
| Customer support | Single agent |
| Enterprise workflow automation | Multi-agent |

---

### ReAct (Reasoning + Acting) Pattern

#### The Core Idea

ReAct interleaves **reasoning traces** (thinking) with **actions** (doing), making the agent's decision-making transparent and correctable.

#### The Pattern

```
Thought: [What I need to figure out / what I know so far]
Action: [Tool call or operation to perform]
Observation: [Result of the action]

Thought: [Updated understanding based on observation]
Action: [Next step]
Observation: [Result]

... (repeat) ...

Thought: [I now have enough information]
Final Answer: [Response to user]
```

#### Concrete Example

```
Question: "Who is the CEO of the company that made the iPhone, and what's their net worth?"

Thought: I need to find who makes the iPhone, then find their CEO, then find net worth.
Action: search("who manufactures the iPhone")
Observation: Apple Inc. manufactures the iPhone.

Thought: Apple makes the iPhone. Now I need their current CEO.
Action: search("Apple Inc CEO 2026")
Observation: Tim Cook is the CEO of Apple Inc.

Thought: Tim Cook is the CEO. Now I need his net worth.
Action: search("Tim Cook net worth 2026")
Observation: Tim Cook's net worth is approximately $1.9 billion.

Thought: I have all the information needed.
Final Answer: Tim Cook is the CEO of Apple (which makes the iPhone),
and his net worth is approximately $1.9 billion.
```

#### Why ReAct Works

1. **Transparency**: You can see why the agent made each decision
2. **Error recovery**: If an observation is wrong, the agent can adjust
3. **Grounding**: Actions provide real data, reducing hallucination
4. **Debugging**: Easy to find where things went wrong in the trace

---

### Plan-and-Execute Agents

#### The Pattern

Unlike ReAct (which interleaves thinking and acting), Plan-and-Execute separates planning from execution:

```
┌──────────────────────────────────────────────┐
│                                              │
│   Phase 1: PLAN                              │
│   ┌────────────────────────────────────┐    │
│   │ 1. Understand the goal             │    │
│   │ 2. Break into sub-tasks            │    │
│   │ 3. Order dependencies              │    │
│   │ 4. Assign tools/methods            │    │
│   └────────────────────────────────────┘    │
│                                              │
│   Phase 2: EXECUTE                           │
│   ┌────────────────────────────────────┐    │
│   │ For each step in plan:             │    │
│   │   - Execute the step               │    │
│   │   - Validate result                │    │
│   │   - If failed: replan from here    │    │
│   └────────────────────────────────────┘    │
│                                              │
└──────────────────────────────────────────────┘
```

#### Example

```
User: "Migrate our user database from MySQL to PostgreSQL"

PLAN:
  1. Analyze current MySQL schema
  2. Generate equivalent PostgreSQL schema
  3. Write data migration scripts
  4. Set up PostgreSQL instance
  5. Run migration on test data
  6. Validate data integrity
  7. Document the process

EXECUTE:
  Step 1: [reads MySQL schema] → Done ✓
  Step 2: [generates PostgreSQL DDL] → Done ✓
  Step 3: [writes migration script] → Done ✓
  Step 4: [configures PostgreSQL] → Error! Permission denied
  
  REPLAN: Need admin credentials → ask user → continue
```

#### Plan-and-Execute vs. ReAct

| Aspect | ReAct | Plan-and-Execute |
|--------|-------|-----------------|
| Planning | Implicit, step-by-step | Explicit upfront plan |
| Adaptability | High (adjusts each step) | Re-plans on failure |
| Best for | Exploratory tasks | Well-structured tasks |
| Overhead | Lower | Higher (planning step) |
| Predictability | Lower | Higher |

---

### Router/Orchestrator Patterns

#### Router Pattern

A lightweight agent that classifies the request and routes to the right specialist:

```
                    ┌─────────────┐
                    │   Router    │
                    │  (Classifies│
                    │   intent)   │
                    └──────┬──────┘
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
    ┌──────────────┐ ┌──────────┐ ┌──────────────┐
    │ Code Agent   │ │ Q&A Agent│ │ Creative     │
    │              │ │          │ │ Agent        │
    └──────────────┘ └──────────┘ └──────────────┘
```

**Use case**: Different types of requests need fundamentally different handling.

#### Orchestrator Pattern

A central agent that coordinates multiple agents, manages state, and assembles results:

```
                    ┌──────────────────┐
                    │   Orchestrator   │
                    │                  │
                    │ - Manages state  │
                    │ - Assigns tasks  │
                    │ - Merges results │
                    │ - Handles errors │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
      ┌─────────────┐ ┌──────────┐ ┌─────────────┐
      │  Research   │ │ Analysis │ │  Synthesis  │
      │  Agent      │ │ Agent    │ │  Agent      │
      └─────────────┘ └──────────┘ └─────────────┘
```

**Use case**: Complex tasks requiring multiple specialists working together.

#### Comparison

| Aspect | Router | Orchestrator |
|--------|--------|-------------|
| Complexity | Low | High |
| Agent interaction | None (single hand-off) | Continuous coordination |
| State management | Minimal | Central state |
| Use case | Classification + dispatch | Complex workflows |
| Example | Customer support triage | Software development pipeline |

---

## Section 3: Practical Building Blocks

---

### Memory Systems

#### Types of Memory

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Memory                          │
│                                                         │
│  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  SHORT-TERM     │  │  LONG-TERM                  │  │
│  │                 │  │                             │  │
│  │ • Context window│  │ • Vector database           │  │
│  │ • Current task  │  │ • User preferences          │  │
│  │ • Recent tools  │  │ • Learned patterns          │  │
│  │ • Conversation  │  │ • Historical interactions   │  │
│  │                 │  │                             │  │
│  │ Duration: mins  │  │ Duration: persistent        │  │
│  └─────────────────┘  └─────────────────────────────┘  │
│                                                         │
│  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  EPISODIC       │  │  SEMANTIC                   │  │
│  │                 │  │                             │  │
│  │ • Past tasks    │  │ • Domain knowledge          │  │
│  │ • What worked   │  │ • Facts and relationships   │  │
│  │ • What failed   │  │ • Concepts and definitions  │  │
│  │ • Strategies    │  │ • Indexed documentation     │  │
│  │                 │  │                             │  │
│  │ Duration: long  │  │ Duration: persistent        │  │
│  └─────────────────┘  └─────────────────────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

#### Implementation Approaches

| Memory Type | Technology | Example |
|-------------|-----------|---------|
| Short-term | Context window / buffer | Last 10 messages |
| Long-term | Vector DB (Pinecone, Chroma) | User preference embeddings |
| Episodic | Structured logs + retrieval | "Last time we did X, approach Y worked" |
| Semantic | Knowledge graph / RAG | Company documentation |

#### Memory in Practice

```python
# Conceptual memory flow
class AgentMemory:
    def store(self, interaction):
        self.short_term.add(interaction)          # Always
        if interaction.is_important():
            self.long_term.embed_and_store(interaction)  # Selective
        if interaction.is_task_completion():
            self.episodic.log(interaction)         # Task outcomes

    def recall(self, query):
        recent = self.short_term.get_context()
        relevant = self.long_term.search(query, top_k=5)
        similar_tasks = self.episodic.find_similar(query)
        return merge(recent, relevant, similar_tasks)
```

---

### Retrieval-Augmented Generation (RAG) in Agents

#### Why RAG?

LLMs have a knowledge cutoff and can't know your private data. RAG bridges this gap:

```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│   User Query: "What's our refund policy for enterprise?"│
│                                                          │
│   ┌──────────┐    ┌──────────────┐    ┌──────────────┐  │
│   │  Query   │───▶│  Retrieval   │───▶│  Generation  │  │
│   │          │    │              │    │              │  │
│   │ Embed    │    │ Search vector│    │ LLM + context│  │
│   │ the query│    │ database for │    │ generates    │  │
│   │          │    │ relevant docs│    │ grounded     │  │
│   │          │    │              │    │ answer       │  │
│   └──────────┘    └──────────────┘    └──────────────┘  │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

#### RAG Pipeline

```
Document Ingestion:
  Documents → Chunk → Embed → Store in Vector DB

Query Time:
  Query → Embed → Search Vector DB → Top-K chunks → LLM → Answer
```

#### RAG in Agents vs. Standalone RAG

| Standalone RAG | RAG in Agents |
|----------------|---------------|
| Single retrieval + generation | Multiple retrievals across steps |
| Static query | Agent reformulates queries based on results |
| One-shot | Iterative — agent decides if it needs more info |
| Fixed pipeline | Agent chooses when to use RAG vs. other tools |

#### Advanced RAG Techniques for Agents

1. **Agentic RAG**: Agent decides what to search, evaluates results, reformulates if needed
2. **Multi-source RAG**: Agent searches across multiple knowledge bases
3. **Self-RAG**: Agent grades its own retrieval quality and retries
4. **Graph RAG**: Uses knowledge graphs for structured retrieval

---

### Guardrails and Safety Layers

#### The Safety Stack

```
┌─────────────────────────────────────────────────┐
│              User Input                          │
└─────────────────────┬───────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────┐
│  Layer 1: INPUT VALIDATION                      │
│  - Prompt injection detection                   │
│  - Content filtering                            │
│  - Rate limiting                                │
│  - Authentication/Authorization                 │
└─────────────────────┬───────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────┐
│  Layer 2: AGENT CONSTRAINTS                     │
│  - Tool access control (what tools can be used) │
│  - Action budgets (max API calls, cost limits)  │
│  - Scope boundaries (don't go off-task)         │
│  - Permission levels (read-only vs. read-write) │
└─────────────────────┬───────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────┐
│  Layer 3: OUTPUT VALIDATION                     │
│  - Factuality checking                          │
│  - Toxicity filtering                           │
│  - PII redaction                                │
│  - Format compliance                            │
└─────────────────────┬───────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────┐
│  Layer 4: MONITORING & AUDIT                    │
│  - Full trace logging                           │
│  - Anomaly detection                            │
│  - Human review triggers                        │
│  - Kill switch capabilities                     │
└─────────────────────────────────────────────────┘
```

#### Common Guardrail Strategies

| Risk | Guardrail | Implementation |
|------|-----------|----------------|
| Prompt injection | Input sanitization + classifier | Dedicated detection model |
| Runaway loops | Iteration limits + cost caps | Max 20 tool calls per task |
| Data leakage | Output filtering + PII detection | Regex + NER models |
| Unauthorized actions | Permission system | Role-based tool access |
| Hallucination | Grounding + citation requirements | Must cite sources |
| Harmful content | Content classifiers | Pre/post generation filters |

---

### Human-in-the-Loop Design

#### Levels of Autonomy

```
Level 0: Human Does Everything
  Agent: [suggests] → Human: [decides + acts]

Level 1: Agent Suggests, Human Approves
  Agent: [plans + proposes] → Human: [approves/rejects] → Agent: [executes]

Level 2: Agent Acts, Human Monitors
  Agent: [plans + executes] → Human: [reviews + can intervene]

Level 3: Agent Autonomous with Exceptions
  Agent: [handles routine autonomously]
  Agent: [escalates edge cases to human]

Level 4: Fully Autonomous
  Agent: [handles everything, reports results]
```

#### When to Insert Human Checkpoints

```
┌─────────────────────────────────────────────────┐
│  INSERT HUMAN CHECKPOINT WHEN:                  │
│                                                 │
│  □ Action is irreversible (delete, send, pay)   │
│  □ Confidence is below threshold                │
│  □ Action affects other people                  │
│  □ Cost exceeds limit                           │
│  □ Task enters unfamiliar territory             │
│  □ Conflicting information found                │
│  □ Security-sensitive operation                  │
│  □ First time performing this type of task      │
│                                                 │
└─────────────────────────────────────────────────┘
```

#### Design Patterns

**Approval Queue**: Agent batches decisions for human review

```
Agent works → [Queue: 5 items need approval] → Human reviews batch → Agent continues
```

**Confidence Threshold**: Agent only asks when uncertain

```
if confidence > 0.9: execute autonomously
if confidence 0.6-0.9: execute but flag for review
if confidence < 0.6: stop and ask human
```

**Progressive Autonomy**: Agent earns trust over time

```
Week 1: Approve every action
Week 2: Approve only risky actions  
Week 3: Monitor only, intervene if needed
Week 4: Fully autonomous for this task type
```

---

## Section 4: Multi-Agent Systems

---

### Agent-to-Agent Communication

#### Communication Patterns

**1. Direct Messaging**
```
[Agent A] ──message──▶ [Agent B]
[Agent B] ──response──▶ [Agent A]
```

**2. Shared Blackboard**
```
[Agent A] ──writes──▶ [Shared State] ◀──reads── [Agent B]
[Agent C] ──writes──▶ [Shared State] ◀──reads── [Agent A]
```

**3. Publish/Subscribe**
```
[Agent A] ──publishes──▶ [Topic: "research_complete"]
                              │
                    ┌─────────┼─────────┐
                    ▼                    ▼
              [Agent B]            [Agent C]
              (subscribed)         (subscribed)
```

#### Message Structure

```json
{
  "from": "research_agent",
  "to": "analysis_agent",
  "type": "task_result",
  "content": {
    "task_id": "research_001",
    "status": "complete",
    "findings": [...],
    "confidence": 0.87,
    "sources": [...]
  },
  "metadata": {
    "timestamp": "2026-05-13T10:30:00Z",
    "tokens_used": 4500
  }
}
```

#### Protocols

| Protocol | Description | Use Case |
|----------|-------------|----------|
| **Request-Response** | Agent asks, other replies | Simple delegation |
| **Task Delegation** | Orchestrator assigns work | Workflow automation |
| **Negotiation** | Agents discuss and agree | Resource allocation |
| **Broadcast** | One agent informs all | Status updates |
| **Streaming** | Continuous data flow | Real-time processing |

---

### Crew/Swarm Architectures

#### Crew Architecture (Structured Teams)

Inspired by how human teams work — defined roles, clear hierarchy:

```
┌───────────────────────────────────────────────────────┐
│                    CREW                                │
│                                                       │
│   ┌─────────────┐                                    │
│   │   Manager   │ ← Assigns tasks, tracks progress   │
│   └──────┬──────┘                                    │
│          │                                           │
│   ┌──────┼──────────────────┐                        │
│   ▼      ▼                  ▼                        │
│ ┌─────┐ ┌──────────┐ ┌──────────┐                   │
│ │Researcher│ │ Developer │ │  Tester  │               │
│ │     │ │          │ │          │                     │
│ │Role:│ │Role:     │ │Role:     │                     │
│ │Find │ │Build     │ │Validate  │                     │
│ │info │ │solution  │ │quality   │                     │
│ └─────┘ └──────────┘ └──────────┘                    │
│                                                       │
│ Workflow: Sequential or Parallel by task              │
└───────────────────────────────────────────────────────┘
```

**Characteristics:**
- Fixed roles defined upfront
- Clear task delegation
- Sequential or parallel workflows
- Shared memory/context between agents

#### Swarm Architecture (Emergent Behavior)

Inspired by biological swarms — simple rules, emergent intelligence:

```
┌───────────────────────────────────────────────────────┐
│                    SWARM                               │
│                                                       │
│     ○ ─── ○ ─── ○                                    │
│     │      │      │                                   │
│     ○ ─── ○ ─── ○         All agents are peers       │
│     │      │      │        No fixed hierarchy         │
│     ○ ─── ○ ─── ○         Self-organizing            │
│                                                       │
│  Rules:                                               │
│  1. Pick up tasks you're suited for                   │
│  2. Share findings with neighbors                     │
│  3. If stuck, pass to another agent                   │
│  4. Aggregate results when enough evidence            │
│                                                       │
└───────────────────────────────────────────────────────┘
```

**Characteristics:**
- No central coordinator
- Agents self-organize
- Handoffs between agents as needed
- Emergent problem-solving

#### Crew vs. Swarm

| Aspect | Crew | Swarm |
|--------|------|-------|
| Structure | Hierarchical | Flat/peer-to-peer |
| Roles | Pre-defined | Dynamic |
| Coordination | Central manager | Self-organizing |
| Predictability | High | Lower |
| Flexibility | Lower | Higher |
| Best for | Known workflows | Exploratory tasks |
| Example framework | CrewAI | OpenAI Swarm |

---

### Specialization and Delegation Patterns

#### Agent Specialization Matrix

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────┐ │
│  │  Research  │ │   Code     │ │  Writing   │ │  Review  │ │
│  │  Agent     │ │   Agent    │ │  Agent     │ │  Agent   │ │
│  ├────────────┤ ├────────────┤ ├────────────┤ ├──────────┤ │
│  │ Model:     │ │ Model:     │ │ Model:     │ │ Model:   │ │
│  │ Opus       │ │ Sonnet     │ │ Sonnet     │ │ Opus     │ │
│  │            │ │            │ │            │ │          │ │
│  │ Tools:     │ │ Tools:     │ │ Tools:     │ │ Tools:   │ │
│  │ - Search   │ │ - Editor   │ │ - Editor   │ │ - Read   │ │
│  │ - Fetch    │ │ - Terminal │ │ - Grammar  │ │ - Lint   │ │
│  │ - Papers   │ │ - Debug    │ │ - Style    │ │ - Test   │ │
│  │            │ │            │ │            │ │          │ │
│  │ System     │ │ System     │ │ System     │ │ System   │ │
│  │ Prompt:    │ │ Prompt:    │ │ Prompt:    │ │ Prompt:  │ │
│  │ "You are   │ │ "You are   │ │ "You are   │ │ "You are │ │
│  │ a research │ │ a senior   │ │ a technical│ │ a code   │ │
│  │ analyst"   │ │ developer" │ │ writer"    │ │ reviewer"│ │
│  └────────────┘ └────────────┘ └────────────┘ └──────────┘ │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

#### Delegation Strategies

**1. Skill-Based Delegation**
```
Task arrives → Assess required skills → Route to most capable agent
```

**2. Load-Based Delegation**
```
Task arrives → Check agent availability → Route to least busy agent
```

**3. Hierarchical Delegation**
```
Complex task → Manager breaks down → Sub-tasks delegated to specialists
```

**4. Auction-Based Delegation**
```
Task announced → Agents "bid" based on capability/availability → Best bid wins
```

---

### Consensus and Conflict Resolution

#### When Agents Disagree

```
Scenario: "Is this code change safe to deploy?"

Agent A (Security): "No — there's a potential SQL injection"
Agent B (Performance): "Yes — it improves query time by 40%"
Agent C (Testing): "Tests pass, but coverage is only 60%"

CONFLICT DETECTED → Resolution needed
```

#### Resolution Strategies

**1. Voting / Majority Rules**
```
3 agents review → 2 say "approve" → Decision: approve
Simple but risks ignoring important minority concerns
```

**2. Weighted Voting**
```
Security agent (weight: 3) says "reject"
Performance agent (weight: 1) says "approve"
Testing agent (weight: 2) says "conditional"

Weighted score → Decision: reject (security concerns outweigh)
```

**3. Debate / Argumentation**
```
Round 1: Each agent presents position + evidence
Round 2: Agents respond to each other's arguments
Round 3: Final positions
Moderator: Synthesizes into decision
```

**4. Escalation to Human**
```
If disagreement > threshold → Present all positions to human → Human decides
Most conservative but most reliable for high-stakes decisions
```

**5. Hierarchical Override**
```
Senior agent can override junior agents
Domain expert has final say in their domain
```

---

## Section 5: Real-World Applications

---

### Coding Agents (Claude Code, Copilot, Cursor)

#### How Coding Agents Work

```
┌─────────────────────────────────────────────────────────┐
│                  Coding Agent                            │
│                                                         │
│   User: "Add authentication to the API"                 │
│                                                         │
│   ┌─────────────────────────────────────────────────┐  │
│   │ 1. READ: Understand existing codebase           │  │
│   │ 2. PLAN: Design authentication approach         │  │
│   │ 3. WRITE: Generate code changes                 │  │
│   │ 4. TEST: Run tests to verify                    │  │
│   │ 5. FIX: Iterate if tests fail                   │  │
│   │ 6. REVIEW: Self-check for quality               │  │
│   └─────────────────────────────────────────────────┘  │
│                                                         │
│   Tools: File read/write, Terminal, Search, Git, LSP    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

#### Comparison of Coding Agents

| Feature | Claude Code | GitHub Copilot | Cursor |
|---------|-------------|----------------|--------|
| Interface | CLI / IDE / Web | IDE Plugin | Full IDE |
| Autonomy | High (agentic) | Medium (suggestions) | High (agentic) |
| Multi-file | Yes | Limited | Yes |
| Terminal access | Yes | No | Yes |
| Planning | Explicit plans | Implicit | Explicit |
| Best for | Complex tasks, CLI workflows | Inline completions | IDE-native workflows |

#### What Makes Coding Agents Different from Autocomplete

| Autocomplete | Coding Agent |
|-------------|--------------|
| Predicts next line | Plans entire features |
| Works in one file | Works across codebase |
| No understanding of project | Reads docs, tests, configs |
| Passive (waits for you) | Active (proposes and executes) |
| No verification | Runs tests, checks errors |

---

### Customer Support Automation

#### Agent Architecture for Support

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   Customer Message                                          │
│        │                                                    │
│        ▼                                                    │
│   ┌──────────┐     ┌─────────────────────────────────────┐ │
│   │  Router  │────▶│  Knowledge Base (RAG)               │ │
│   │  Agent   │     │  - Product docs                     │ │
│   └────┬─────┘     │  - FAQ                              │ │
│        │           │  - Past tickets                     │ │
│        │           └─────────────────────────────────────┘ │
│        │                                                    │
│   ┌────┼────────────────┐                                  │
│   ▼    ▼                ▼                                  │
│ [Billing] [Technical] [General]                             │
│  Agent     Agent       Agent                                │
│   │         │            │                                  │
│   ▼         ▼            ▼                                  │
│ [CRM]   [Jira]      [Response]                             │
│ [Stripe] [Logs]                                             │
│                                                             │
│   Escalation: confidence < 0.7 → human agent               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Metrics That Matter

| Metric | Without Agent | With Agent |
|--------|--------------|-----------|
| First response time | 4 hours | < 30 seconds |
| Resolution rate (auto) | 0% | 40-60% |
| Human agent load | 100% | 40-60% |
| Customer satisfaction | Baseline | +15-25% |
| Cost per ticket | $15-25 | $2-5 |

---

### Data Analysis Pipelines

#### Agent-Driven Analysis

```
User: "Analyze our Q1 sales data and find the top growth opportunities"

┌────────────────────────────────────────────────────────────┐
│                                                            │
│  Step 1: DATA DISCOVERY                                    │
│  Agent identifies relevant tables/files                    │
│  → Found: sales_q1.csv, customers.db, market_data API     │
│                                                            │
│  Step 2: DATA EXPLORATION                                  │
│  Agent writes and runs exploratory queries                 │
│  → "SELECT region, SUM(revenue)... GROUP BY region"        │
│  → Generates summary statistics                            │
│                                                            │
│  Step 3: ANALYSIS                                          │
│  Agent identifies patterns and anomalies                   │
│  → "Region X grew 45% while others averaged 12%"          │
│  → "Product category Y has highest margin but lowest volume" │
│                                                            │
│  Step 4: VISUALIZATION                                     │
│  Agent generates charts and graphs                         │
│  → Bar charts, trend lines, heatmaps                       │
│                                                            │
│  Step 5: INSIGHT SYNTHESIS                                 │
│  Agent produces actionable recommendations                 │
│  → "Top 3 growth opportunities: ..."                       │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

---

### Autonomous Research Agents

#### Research Agent Flow

```
Query: "What are the latest advances in protein folding prediction?"

┌─────────────────────────────────────────────────────┐
│                                                     │
│   ┌───────────┐                                    │
│   │  Planner  │ → Defines research questions       │
│   └─────┬─────┘                                    │
│         ▼                                          │
│   ┌───────────┐                                    │
│   │  Searcher │ → Queries multiple sources         │
│   │           │   (arXiv, PubMed, Google Scholar)  │
│   └─────┬─────┘                                    │
│         ▼                                          │
│   ┌───────────┐                                    │
│   │  Reader   │ → Reads and extracts key findings  │
│   └─────┬─────┘                                    │
│         ▼                                          │
│   ┌───────────┐                                    │
│   │  Critic   │ → Evaluates quality and relevance  │
│   └─────┬─────┘                                    │
│         ▼                                          │
│   ┌───────────┐                                    │
│   │  Writer   │ → Synthesizes into coherent report │
│   └───────────┘                                    │
│                                                     │
└─────────────────────────────────────────────────────┘
```

#### Capabilities

- Search across multiple academic databases
- Read and summarize papers
- Identify contradictions between sources
- Track citation networks
- Generate literature reviews
- Identify research gaps

---

## Section 6: Challenges & Open Problems

---

### Hallucination and Error Propagation

#### The Cascading Error Problem

```
Step 1: Agent searches for info → Gets slightly wrong fact ✗
Step 2: Agent reasons based on wrong fact → Flawed conclusion ✗✗
Step 3: Agent takes action based on flawed conclusion → Wrong action ✗✗✗
Step 4: Agent builds on wrong action → Compounding error ✗✗✗✗

Each step amplifies the original error!
```

#### Mitigation Strategies

| Strategy | How It Works | Effectiveness |
|----------|-------------|---------------|
| **Grounding** | Always cite sources, verify claims | High |
| **Self-verification** | Agent checks its own work | Medium |
| **Multi-agent validation** | Different agent verifies | High |
| **Human checkpoints** | Human reviews critical steps | Very High |
| **Confidence scoring** | Agent rates its own certainty | Medium |
| **Chain-of-verification** | Explicit verification steps | High |

#### Example: Self-Verification Pattern

```
Agent generates answer: "The company was founded in 2015"
    │
    ▼
Agent verifies: search("company founding date")
    │
    ▼
Search result: "Founded in 2013"
    │
    ▼
Agent corrects: "The company was founded in 2013"
```

---

### Evaluation and Benchmarking Agents

#### Why It's Hard

- Non-deterministic outputs (same input → different paths)
- Process matters, not just final answer
- Real-world tasks don't have single correct answers
- Tool interactions are hard to mock

#### Evaluation Dimensions

```
┌─────────────────────────────────────────────────────┐
│           Agent Evaluation Framework                 │
│                                                     │
│   ┌─────────────┐  ┌──────────────┐  ┌──────────┐ │
│   │  ACCURACY   │  │  EFFICIENCY  │  │  SAFETY  │ │
│   │             │  │              │  │          │ │
│   │ • Correct?  │  │ • Steps taken│  │ • Harm?  │ │
│   │ • Complete? │  │ • Cost       │  │ • Leaks? │ │
│   │ • Relevant? │  │ • Latency    │  │ • Scope? │ │
│   └─────────────┘  └──────────────┘  └──────────┘ │
│                                                     │
│   ┌─────────────┐  ┌──────────────┐  ┌──────────┐ │
│   │ ROBUSTNESS  │  │  USABILITY   │  │  TRUST   │ │
│   │             │  │              │  │          │ │
│   │ • Edge cases│  │ • Clear?     │  │ • Cited? │ │
│   │ • Failures? │  │ • Helpful?   │  │ • Honest?│ │
│   │ • Recovery? │  │ • Aligned?   │  │ • Know   │ │
│   │             │  │              │  │   limits?│ │
│   └─────────────┘  └──────────────┘  └──────────┘ │
│                                                     │
└─────────────────────────────────────────────────────┘
```

#### Benchmarking Approaches

| Approach | Description | Limitation |
|----------|-------------|-----------|
| **Task completion** | Did it finish the job? | Binary, misses quality |
| **Human evaluation** | Experts rate quality | Expensive, slow |
| **Automated metrics** | BLEU, ROUGE, pass@k | Doesn't capture reasoning |
| **Trajectory analysis** | Evaluate each step | Complex to implement |
| **A/B testing** | Compare agent versions | Needs production traffic |
| **SWE-bench style** | Real-world task suites | Limited task diversity |

---

### Cost and Latency Management

#### The Cost Equation

```
Total Cost = (Input tokens × price) + (Output tokens × price) × Number of steps
           + Tool call costs + Infrastructure

Example:
  Simple query: 1 LLM call = $0.01
  Agent task: 15 LLM calls + 8 tool calls = $0.50-$2.00
  Complex workflow: 50+ LLM calls = $5.00-$20.00
```

#### Optimization Strategies

| Strategy | Savings | Trade-off |
|----------|---------|-----------|
| **Model routing** | 50-70% | Smaller models may be less capable |
| **Caching** | 30-60% | Stale results possible |
| **Prompt compression** | 20-40% | May lose context |
| **Early stopping** | Variable | May miss better answers |
| **Parallel execution** | Latency only | Same cost, faster results |
| **Batch processing** | 50% | Higher latency |

#### Model Routing Example

```
┌──────────────┐
│ Task arrives  │
└──────┬───────┘
       ▼
┌──────────────────┐
│ Complexity check  │
└──────┬───────────┘
       │
       ├── Simple → Haiku ($0.001/call)    — "What time is it in London?"
       ├── Medium → Sonnet ($0.01/call)    — "Summarize this document"
       └── Complex → Opus ($0.05/call)     — "Design a system architecture"
```

#### Latency Breakdown

```
Typical Agent Task (15 seconds total):

  Planning:    ████░░░░░░ (3s) — LLM reasoning
  Tool calls:  ██████░░░░ (6s) — API calls, search, etc.
  Processing:  ████░░░░░░ (4s) — LLM processing results
  Overhead:    ██░░░░░░░░ (2s) — Network, serialization
```

---

### When NOT to Use Agents

#### The Decision Matrix

```
                    High Reasoning Required
                           │
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         │   Copilot /     │    AGENT ✓      │
         │   Assisted      │                 │
         │                 │                 │
   Few ──┼─────────────────┼─────────────────┼── Many
  Steps  │                 │                 │  Steps
         │   Simple LLM    │   Workflow      │
         │   Call          │   Engine        │
         │                 │                 │
         └─────────────────┼─────────────────┘
                           │
                    Low Reasoning Required
```

#### Red Flags: Don't Use an Agent

1. **Deterministic process**: If you can write it as a flowchart with no ambiguity → use a script
2. **Sub-second requirement**: Agents are slow (5-60s) → use cached/precomputed
3. **Zero error tolerance**: Agents make mistakes → use rule-based systems
4. **Simple CRUD**: No reasoning needed → use traditional APIs
5. **Cost-sensitive at scale**: 1M requests/day × $0.50/agent = $500K/day → optimize first
6. **Sensitive operations without oversight**: Agents + irreversible actions = risk

#### The Right Tool for the Job

| Task | Best Approach |
|------|--------------|
| "Send email when order ships" | Simple automation |
| "Categorize this support ticket" | Single LLM call |
| "Write a test for this function" | Coding agent |
| "Analyze competitor pricing weekly" | Scheduled agent workflow |
| "Process 10M log lines" | Traditional data pipeline |
| "Debug why the deploy failed" | Agent with human-in-loop |

---

## Section 7: Live Demo Ideas

---

### Demo 1: Build a Simple ReAct Agent from Scratch

#### Minimal Implementation (Python-like pseudocode)

```python
import anthropic

client = anthropic.Anthropic()

tools = [
    {
        "name": "search",
        "description": "Search the web for information",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "calculate",
        "description": "Perform mathematical calculations",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string"}
            },
            "required": ["expression"]
        }
    }
]

def run_agent(user_query):
    messages = [{"role": "user", "content": user_query}]
    
    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            tools=tools,
            messages=messages
        )
        
        # Check if agent wants to use a tool
        if response.stop_reason == "tool_use":
            tool_call = next(b for b in response.content if b.type == "tool_use")
            tool_result = execute_tool(tool_call.name, tool_call.input)
            
            # Add assistant response and tool result to messages
            messages.append({"role": "assistant", "content": response.content})
            messages.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": tool_call.id, "content": tool_result}]
            })
        else:
            # Agent is done — return final answer
            return response.content[0].text

# Run it
answer = run_agent("What's the population of France divided by the area of Texas?")
print(answer)
```

#### What to Show the Audience
- The loop structure (while True → call LLM → check for tool use → execute → repeat)
- How the LLM decides which tool to use
- The reasoning trace in the response
- How it handles multi-step problems

---

### Demo 2: Multi-Agent Debate/Collaboration

#### Concept

Two or more agents debate a topic, building on each other's arguments:

```python
def run_debate(topic, rounds=3):
    agent_a_messages = []  # Pro position
    agent_b_messages = []  # Con position
    
    # System prompts define positions
    system_a = "You argue IN FAVOR of the topic. Be concise and evidence-based."
    system_b = "You argue AGAINST the topic. Be concise and evidence-based."
    
    debate_log = []
    
    for round in range(rounds):
        # Agent A argues
        a_response = call_llm(system_a, agent_a_messages + 
                             [{"role": "user", "content": f"Round {round+1}. Topic: {topic}. "
                              f"Opponent's last argument: {debate_log[-1] if debate_log else 'None'}"}])
        debate_log.append(f"PRO: {a_response}")
        
        # Agent B responds
        b_response = call_llm(system_b, agent_b_messages +
                             [{"role": "user", "content": f"Round {round+1}. Topic: {topic}. "
                              f"Opponent's last argument: {a_response}"}])
        debate_log.append(f"CON: {b_response}")
    
    # Judge agent synthesizes
    judge_response = call_llm(
        "You are an impartial judge. Evaluate both sides and declare a winner with reasoning.",
        [{"role": "user", "content": "\n".join(debate_log)}]
    )
    
    return debate_log, judge_response
```

#### Good Demo Topics
- "Should we rewrite this legacy system from scratch?"
- "Is microservices always better than monolith?"
- "Should AI agents be allowed to write production code without human review?"

---

### Demo 3: Tool-Using Agent with MCP Servers

#### What is MCP (Model Context Protocol)?

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│   ┌──────────┐     MCP Protocol     ┌──────────────┐  │
│   │  Agent   │◀═══════════════════▶│  MCP Server  │  │
│   │ (Client) │                      │              │  │
│   └──────────┘                      │ Exposes:     │  │
│                                     │ - Tools      │  │
│                                     │ - Resources  │  │
│                                     │ - Prompts    │  │
│                                     └──────────────┘  │
│                                                         │
│   MCP = Universal adapter between AI agents and tools   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

#### MCP Architecture

```
┌─────────────┐
│   Agent     │
└──────┬──────┘
       │ MCP Protocol
       │
┌──────┼──────────────────────────────────────┐
│      │         MCP Servers                   │
│      │                                       │
│  ┌───┴───┐  ┌─────────┐  ┌──────────────┐  │
│  │GitHub │  │Database │  │ Filesystem  │  │
│  │Server │  │Server   │  │ Server      │  │
│  │       │  │         │  │             │  │
│  │Tools: │  │Tools:   │  │Tools:       │  │
│  │-create│  │-query   │  │-read_file   │  │
│  │ issue │  │-insert  │  │-write_file  │  │
│  │-PR    │  │-schema  │  │-list_dir    │  │
│  └───────┘  └─────────┘  └──────────────┘  │
│                                              │
└──────────────────────────────────────────────┘
```

#### Demo Flow

```
1. Start MCP server (e.g., filesystem server)
2. Agent connects and discovers available tools
3. Give agent a task: "Organize my downloads folder by file type"
4. Watch agent:
   - List directory contents (tool: list_dir)
   - Categorize files by extension
   - Create subdirectories (tool: create_dir)
   - Move files (tool: move_file)
   - Report what was done
```

#### Why MCP Matters

| Before MCP | After MCP |
|------------|-----------|
| Custom integration per tool | Standardized protocol |
| Agent locked to specific tools | Plug-and-play any MCP server |
| Hard to share tool implementations | Community ecosystem of servers |
| Each framework reinvents the wheel | Universal standard |

---

## Appendix: Frameworks and Tools Reference

| Framework | Language | Best For | Key Feature |
|-----------|----------|----------|-------------|
| **LangGraph** | Python/JS | Complex agent workflows | Graph-based state machines |
| **CrewAI** | Python | Multi-agent teams | Role-based collaboration |
| **AutoGen** | Python | Research/conversation agents | Multi-agent conversations |
| **Claude Agent SDK** | Python | Building on Claude | Native Anthropic integration |
| **Semantic Kernel** | C#/Python | Enterprise agents | Microsoft ecosystem |
| **Haystack** | Python | RAG + Agents | Pipeline architecture |
| **Swarm** | Python | Simple multi-agent | Lightweight handoffs |

---

## Appendix: Glossary

| Term | Definition |
|------|-----------|
| **Agent** | An AI system that can autonomously plan and execute multi-step tasks |
| **Tool** | An external capability (API, function) that an agent can invoke |
| **ReAct** | A pattern interleaving reasoning traces with actions |
| **MCP** | Model Context Protocol — standard for agent-tool communication |
| **RAG** | Retrieval-Augmented Generation — grounding LLM output in retrieved data |
| **Guardrails** | Safety constraints that limit agent behavior |
| **Orchestrator** | An agent that coordinates other agents |
| **Hallucination** | When an LLM generates plausible but incorrect information |
| **Grounding** | Anchoring agent outputs in verified external data |
| **Context window** | The maximum amount of text an LLM can process at once |
| **Function calling** | The ability for an LLM to request execution of defined functions |
| **Agentic loop** | The iterative cycle of reasoning and acting until a goal is met |

---

*Generated: May 2026*
