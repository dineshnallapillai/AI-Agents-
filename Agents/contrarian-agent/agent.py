"""
Contrarian Agent
=================
An AI agent that challenges your decisions by autonomously researching
counterarguments, risks, and alternatives you haven't considered.

Give it any decision you're about to make (job offer, architecture choice,
purchase, strategy) and it will:
  1. Break it into dimensions worth challenging
  2. Search for counterarguments and risks
  3. Find alternatives you may not have considered
  4. Cross-reference across multiple sources
  5. Deliver a structured contrarian report

Stack: Python + Claude (via AWS Bedrock) + DuckDuckGo + BeautifulSoup
Auth: AWS SSO via boto3 Session (same pattern as knowledge-base-agent)

Usage:
  python agent.py "I'm thinking of accepting a job at a startup over BigCorp"
  python agent.py --interactive
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime
from pathlib import Path

import boto3
import anthropic
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

from config import (
    AWS_REGION,
    AWS_PROFILE,
    BEDROCK_APP_PROFILE_ARN,
    MODEL_ID,
    MAX_ITERATIONS,
    MAX_TOKENS,
)

# ============================================================================
# BEDROCK AUTH (same pattern as knowledge-base-agent)
# ============================================================================


def get_bedrock_client():
    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    credentials = session.get_credentials().get_frozen_credentials()

    return anthropic.AnthropicBedrock(
        aws_access_key=credentials.access_key,
        aws_secret_key=credentials.secret_key,
        aws_session_token=credentials.token,
        aws_region=AWS_REGION,
    )


# ============================================================================
# TOOLS — what the agent can do
# ============================================================================


def web_search(query: str, max_results: int = 5) -> str:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return json.dumps({"results": [], "message": "No results found."})
        return json.dumps({"results": [
            {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
            for r in results
        ]})
    except Exception as e:
        return json.dumps({"error": str(e)})


def read_webpage(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        content = "\n".join(lines)

        if len(content) > 6000:
            content = content[:6000] + "\n\n[...truncated]"

        return json.dumps({"url": url, "content": content})
    except Exception as e:
        return json.dumps({"url": url, "error": str(e)})


findings_store = []


def note_finding(finding: str, category: str, confidence: str, source: str = "") -> str:
    entry = {
        "finding": finding,
        "category": category,
        "confidence": confidence,
        "source": source,
        "timestamp": datetime.now().isoformat(),
    }
    findings_store.append(entry)
    return json.dumps({"status": "noted", "total_findings": len(findings_store)})


def save_report(title: str, summary: str, sections: str) -> str:
    report_dir = Path(__file__).parent / "reports"
    report_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"contrarian_{timestamp}.md"
    filepath = report_dir / filename

    report_content = f"""# {title}

*Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*

## Summary

{summary}

{sections}

---

## Research Notes

| # | Finding | Category | Confidence | Source |
|---|---------|----------|------------|--------|
"""
    for i, f in enumerate(findings_store, 1):
        source_text = f.get("source", "")
        report_content += f"| {i} | {f['finding'][:80]} | {f['category']} | {f['confidence']} | {source_text[:50]} |\n"

    filepath.write_text(report_content, encoding="utf-8")

    print(f"\n{'='*60}")
    print(report_content)
    print(f"{'='*60}")
    print(f"\nReport saved to: {filepath}")

    return json.dumps({"status": "saved", "path": str(filepath), "findings_count": len(findings_store)})


# Tool definitions for Claude
TOOLS = [
    {
        "name": "web_search",
        "description": (
            "Search the web using DuckDuckGo. Use this to find counterarguments, "
            "risks, alternatives, statistics, expert opinions, and real-world "
            "experiences related to the user's decision."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "max_results": {"type": "integer", "description": "Number of results (default 5)", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_webpage",
        "description": (
            "Fetch and read the text content of a webpage. Use this to get detailed "
            "information from a search result — articles, forum posts, reviews, "
            "comparisons, and expert analyses."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to read"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "note_finding",
        "description": (
            "Save an intermediate research finding. Use this to build up evidence "
            "as you research. Each finding should be a specific fact, risk, "
            "counterargument, or alternative with its source."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "finding": {"type": "string", "description": "The specific finding or insight"},
                "category": {
                    "type": "string",
                    "description": "One of: risk, counterargument, alternative, statistic, expert_opinion, experience",
                },
                "confidence": {
                    "type": "string",
                    "description": "One of: high, medium, low — based on source quality and corroboration",
                },
                "source": {"type": "string", "description": "URL or description of where this came from"},
            },
            "required": ["finding", "category", "confidence"],
        },
    },
    {
        "name": "save_report",
        "description": (
            "Save the final structured contrarian report. Call this ONLY when "
            "you have gathered enough evidence (at least 5-8 findings across "
            "multiple categories). The report should challenge the user's decision "
            "with evidence-backed counterarguments."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Report title (e.g., 'Contrarian Take: Accepting Startup Offer')"},
                "summary": {
                    "type": "string",
                    "description": "2-3 sentence executive summary of the strongest counterarguments and alternatives",
                },
                "sections": {
                    "type": "string",
                    "description": (
                        "Full markdown body with sections like: "
                        "## Key Risks, ## Counterarguments, ## Alternatives to Consider, "
                        "## What Could Go Wrong, ## Questions to Ask Yourself, ## Final Verdict"
                    ),
                },
            },
            "required": ["title", "summary", "sections"],
        },
    },
]

TOOL_DISPATCH = {
    "web_search": lambda **kwargs: web_search(**kwargs),
    "read_webpage": lambda **kwargs: read_webpage(**kwargs),
    "note_finding": lambda **kwargs: note_finding(**kwargs),
    "save_report": lambda **kwargs: save_report(**kwargs),
}

# ============================================================================
# SYSTEM PROMPT — the real differentiator
# ============================================================================

SYSTEM_PROMPT = """You are the Contrarian Agent. Your job is to challenge the user's decision by finding evidence-backed counterarguments, hidden risks, and alternatives they may not have considered.

You are NOT a yes-man. You are a rigorous devil's advocate who searches for real evidence.

## Your Process:

1. **Decompose the decision** into 3-5 dimensions worth investigating (e.g., financial, career growth, lifestyle, risk tolerance, opportunity cost)

2. **Research each dimension** by:
   - Searching with multiple different queries (try at least 3-4 searches)
   - Reading the most promising articles/posts for details
   - Looking for statistics, expert opinions, and real experiences
   - Searching specifically for failure cases and regrets

3. **Cross-reference findings** — a claim backed by 2-3 sources gets "high" confidence. Single-source claims get "medium" or "low".

4. **Note findings as you go** — use note_finding for every significant insight. Aim for 8-12 findings minimum across categories: risk, counterargument, alternative, statistic, expert_opinion, experience.

5. **Write the final report** with save_report when you have enough evidence. Structure it as:
   - Executive summary (2-3 sentences, the strongest case AGAINST the decision)
   - Key Risks (what could go wrong, with evidence)
   - Counterarguments (why the opposite choice might be better)
   - Alternatives to Consider (options the user may not have thought of)
   - What Could Go Wrong (worst-case scenarios with real examples)
   - Questions to Ask Yourself (probing questions to stress-test the decision)
   - Final Verdict (your honest assessment: proceed, reconsider, or abandon — with confidence level)

## Rules:
- Always search before forming opinions
- Distinguish facts from opinions in your findings
- Cite sources for every major claim
- Be specific — "startups are risky" is weak; "42% of startups fail within 3 years (CB Insights 2023)" is strong
- If you can't find evidence against the decision, say so honestly — some decisions are clearly good
- Don't pad the report — only include findings backed by evidence
- Use note_finding EVERY time you discover something noteworthy"""


# ============================================================================
# AGENTIC LOOP
# ============================================================================


class CostTracker:
    def __init__(self):
        self.total_input = 0
        self.total_output = 0
        self.total_cache_read = 0
        self.total_cache_write = 0
        self.iterations = 0

    def add(self, usage):
        self.total_input += getattr(usage, "input_tokens", 0) or 0
        self.total_output += getattr(usage, "output_tokens", 0) or 0
        self.total_cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.total_cache_write += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.iterations += 1

    @property
    def estimated_cost(self):
        return (
            self.total_input * 15.00 / 1_000_000
            + self.total_output * 75.00 / 1_000_000
            + self.total_cache_read * 1.50 / 1_000_000
            + self.total_cache_write * 18.75 / 1_000_000
        )

    def summary(self):
        return (
            f"Iterations: {self.iterations} | "
            f"Tokens — in: {self.total_input:,}, out: {self.total_output:,}, "
            f"cache_r: {self.total_cache_read:,}, cache_w: {self.total_cache_write:,} | "
            f"Est. cost: ${self.estimated_cost:.4f}"
        )


def run_agent(decision: str):
    global findings_store
    findings_store = []

    client = get_bedrock_client()
    cost = CostTracker()

    messages = [
        {"role": "user", "content": f"Here is the decision I need a second opinion on:\n\n{decision}"}
    ]

    print(f"\n{'='*60}")
    print(f"CONTRARIAN AGENT")
    print(f"{'='*60}")
    print(f"Decision: {decision}")
    print(f"Model: {MODEL_ID[:50]}...")
    print(f"Max iterations: {MAX_ITERATIONS}")
    print(f"{'='*60}\n")

    for iteration in range(1, MAX_ITERATIONS + 1):
        print(f"[Iteration {iteration}/{MAX_ITERATIONS}]", end=" ")

        response = client.messages.create(
            model=MODEL_ID,
            max_tokens=MAX_TOKENS,
            tools=TOOLS,
            messages=messages,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
        )

        cost.add(response.usage)

        assistant_content = response.content
        messages.append({"role": "assistant", "content": assistant_content})

        if response.stop_reason == "end_turn":
            text_parts = [b.text for b in response.content if hasattr(b, "text")]
            if text_parts:
                print("Done — final response.")
                print("\n" + "\n".join(text_parts))
            else:
                print("Done.")
            break

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input
                print(f"  -> {tool_name}({json.dumps(tool_input)[:80]}...)")

                fn = TOOL_DISPATCH.get(tool_name)
                if fn:
                    result = fn(**tool_input)
                else:
                    result = json.dumps({"error": f"Unknown tool: {tool_name}"})

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        if tool_results:
            messages.append({"role": "user", "content": tool_results})
        else:
            print("No tool calls, no end_turn — stopping.")
            break

    print(f"\n{'='*60}")
    print(f"AGENT COMPLETE")
    print(f"{cost.summary()}")
    print(f"Findings collected: {len(findings_store)}")
    print(f"{'='*60}")


# ============================================================================
# CLI
# ============================================================================


def interactive_mode():
    print("\n" + "="*60)
    print("CONTRARIAN AGENT — Interactive Mode")
    print("="*60)
    print("\nDescribe a decision you're considering.")
    print("The more context you give, the better the contrarian take.")
    print("Type 'quit' to exit.\n")

    while True:
        try:
            decision = input("Your decision: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not decision:
            continue
        if decision.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        run_agent(decision)
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Contrarian Agent — challenges your decisions with evidence"
    )
    parser.add_argument(
        "decision",
        nargs="?",
        default=None,
        help="The decision to get a second opinion on (wrap in quotes)",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive mode (ask multiple questions)",
    )
    args = parser.parse_args()

    if args.interactive:
        interactive_mode()
    elif args.decision:
        run_agent(args.decision)
    else:
        parser.print_help()
        print("\nExamples:")
        print('  python agent.py "Should I accept a startup offer over BigCorp?"')
        print('  python agent.py "I want to rewrite our monolith in microservices"')
        print('  python agent.py "Thinking of buying a $3000 standing desk"')
        print('  python agent.py --interactive')


if __name__ == "__main__":
    main()
