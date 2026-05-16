"""
Batch Code Agent — A Claude Code-like agent using the Message Batches API or AWS Bedrock.

Supports two backends:
- "anthropic": Uses Message Batches API (50% cost reduction, higher latency)
- "bedrock": Uses AWS Bedrock Messages API (standard pricing, normal latency)
"""

import os
import sys
import time

import anthropic
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.live import Live

from tools import TOOL_DEFINITIONS, execute_tool
from config import (
    BACKEND,
    AWS_REGION,
    AWS_PROFILE,
    BEDROCK_MODELS,
    ANTHROPIC_MODELS,
    MODEL_CHOICE,
    MAX_TOKENS,
    POLL_INTERVAL,
    MAX_TURNS,
    PRICING,
    BATCH_DISCOUNT,
)

console = Console()

SYSTEM_PROMPT = """You are a coding assistant that helps with software engineering tasks.
You have access to tools to read, write, and edit files, run bash commands, and search codebases.
Be concise. Focus on solving the task. Use tools when needed.
When you're done, explain what you did briefly."""


def get_model_id() -> str:
    if BACKEND == "bedrock":
        return BEDROCK_MODELS[MODEL_CHOICE]
    return ANTHROPIC_MODELS[MODEL_CHOICE]


def create_client():
    """Create the appropriate client based on backend config."""
    if BACKEND == "bedrock":
        kwargs = {"region": AWS_REGION}
        if AWS_PROFILE:
            import boto3

            session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
            kwargs = {"session": session}

        return anthropic.AnthropicBedrock(**kwargs)
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            console.print(
                "[red]Error: ANTHROPIC_API_KEY environment variable not set.[/red]"
            )
            console.print("Set it with: export ANTHROPIC_API_KEY=your-key-here")
            sys.exit(1)
        return anthropic.Anthropic(api_key=api_key)


def send_message(client, messages: list, system: str) -> dict:
    """Send a message using the appropriate backend. Returns response dict."""
    model_id = get_model_id()

    if BACKEND == "bedrock":
        return _send_bedrock(client, messages, system, model_id)
    else:
        return _send_batch(client, messages, system, model_id)


def _send_bedrock(client, messages: list, system: str, model_id: str) -> dict:
    """Send via AWS Bedrock (real-time, normal latency)."""
    response = client.messages.create(
        model=model_id,
        max_tokens=MAX_TOKENS,
        system=system,
        tools=TOOL_DEFINITIONS,
        messages=messages,
    )
    return response.model_dump()


def _send_batch(client, messages: list, system: str, model_id: str) -> dict:
    """Send via Anthropic Batch API (50% off, higher latency)."""
    batch = client.messages.batches.create(
        requests=[
            {
                "custom_id": "agent-turn",
                "params": {
                    "model": model_id,
                    "max_tokens": MAX_TOKENS,
                    "system": system,
                    "tools": TOOL_DEFINITIONS,
                    "messages": messages,
                },
            }
        ]
    )

    # Poll for completion
    with Live(
        Panel("[yellow]Batch processing...[/yellow]", title="Status"),
        console=console,
        refresh_per_second=2,
    ) as live:
        while True:
            batch_status = client.messages.batches.retrieve(batch.id)
            if batch_status.processing_status == "ended":
                live.update(
                    Panel("[green]Batch complete[/green]", title="Status")
                )
                break
            elapsed = (
                batch_status.request_counts.succeeded
                + batch_status.request_counts.errored
                + batch_status.request_counts.canceled
                + batch_status.request_counts.expired
            )
            total = batch_status.request_counts.processing + elapsed
            live.update(
                Panel(
                    f"[yellow]Processing... ({elapsed}/{total} done)[/yellow]",
                    title="Status",
                )
            )
            time.sleep(POLL_INTERVAL)

    results = list(client.messages.batches.results(batch.id))
    if not results:
        return {"error": "No results returned from batch"}

    result = results[0]
    if result.result.type == "succeeded":
        return result.result.message.model_dump()
    elif result.result.type == "errored":
        return {"error": f"Batch errored: {result.result.error}"}
    else:
        return {"error": f"Batch status: {result.result.type}"}


def extract_response(response: dict) -> tuple[str, list[dict], str]:
    """Extract text, tool calls, and stop reason from response."""
    text_parts = []
    tool_calls = []
    stop_reason = response.get("stop_reason", "end_turn")

    for block in response.get("content", []):
        if block["type"] == "text":
            text_parts.append(block["text"])
        elif block["type"] == "tool_use":
            tool_calls.append(block)

    return "\n".join(text_parts), tool_calls, stop_reason


def run_agent_loop(client, task: str, working_dir: str) -> None:
    """Main agent loop: send → execute tools → repeat."""
    messages = [{"role": "user", "content": task}]

    system = SYSTEM_PROMPT + f"\n\nWorking directory: {working_dir}"

    # Load CLAUDE.md if present
    claude_md_path = os.path.join(working_dir, "CLAUDE.md")
    if os.path.exists(claude_md_path):
        with open(claude_md_path, "r", encoding="utf-8") as f:
            claude_md = f.read()
        system += f"\n\n# Project Instructions (CLAUDE.md)\n{claude_md}"

    turn = 0
    total_input_tokens = 0
    total_output_tokens = 0

    while turn < MAX_TURNS:
        turn += 1
        console.print(f"\n[dim]-- Turn {turn} --[/dim]")

        # Send request
        response = send_message(client, messages, system)

        if "error" in response:
            console.print(f"[red]Error: {response['error']}[/red]")
            break

        # Track tokens
        usage = response.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        total_input_tokens += input_tokens
        total_output_tokens += output_tokens

        console.print(
            f"[dim]Tokens: {input_tokens} in"
            + (f" ({cache_read} cached)" if cache_read else "")
            + f" / {output_tokens} out[/dim]"
        )

        # Extract response
        text, tool_calls, stop_reason = extract_response(response)

        # Display text
        if text:
            console.print()
            console.print(Markdown(text))

        # If no tool calls, we're done
        if stop_reason == "end_turn" or not tool_calls:
            break

        # Execute tools
        assistant_content = response["content"]
        messages.append({"role": "assistant", "content": assistant_content})

        tool_results = []
        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_input = tool_call["input"]
            tool_id = tool_call["id"]

            console.print(f"\n[cyan]> {tool_name}[/cyan]", end="")
            display_key = {
                "bash": "command",
                "read_file": "file_path",
                "write_file": "file_path",
                "edit_file": "file_path",
                "glob_search": "pattern",
                "grep_search": "pattern",
            }.get(tool_name, "")
            if display_key:
                console.print(
                    f"[dim] {tool_input.get(display_key, '')[:80]}[/dim]"
                )
            else:
                console.print()

            result = execute_tool(tool_name, tool_input, working_dir)

            result_preview = result[:200] + "..." if len(result) > 200 else result
            console.print(f"[dim]{result_preview}[/dim]")

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result,
                }
            )

        messages.append({"role": "user", "content": tool_results})

    # Cost summary
    pricing = PRICING[MODEL_CHOICE]
    discount = BATCH_DISCOUNT if BACKEND == "anthropic" else 1.0
    input_cost = total_input_tokens * pricing["input"] * discount / 1_000_000
    output_cost = total_output_tokens * pricing["output"] * discount / 1_000_000
    total_cost = input_cost + output_cost
    realtime_cost = total_input_tokens * pricing["input"] / 1_000_000 + \
                    total_output_tokens * pricing["output"] / 1_000_000

    console.print("\n")
    console.print(
        Panel(
            f"[green]Session complete[/green]\n"
            f"Turns: {turn}\n"
            f"Total input tokens: {total_input_tokens:,}\n"
            f"Total output tokens: {total_output_tokens:,}\n"
            f"Model: {get_model_id()}\n"
            f"Backend: {BACKEND}\n\n"
            f"Cost:\n"
            f"  Input:  ${input_cost:.4f}\n"
            f"  Output: ${output_cost:.4f}\n"
            f"  Total:  ${total_cost:.4f}\n"
            + (
                f"\n  (Batch discount applied: 50% off)\n"
                f"  Real-time equivalent: ${realtime_cost:.4f}\n"
                f"  You saved: ${realtime_cost - total_cost:.4f}"
                if BACKEND == "anthropic"
                else ""
            ),
            title="Session Summary",
        )
    )


def main():
    working_dir = os.getcwd()

    console.print(
        Panel(
            "[bold]Batch Code Agent[/bold]\n"
            f"Backend: {BACKEND}\n"
            f"Model: {get_model_id()}\n"
            f"Working dir: {working_dir}\n\n"
            "[dim]Type your task, or 'quit' to exit.[/dim]",
            title="Batch Code Agent",
        )
    )

    client = create_client()

    while True:
        console.print()
        task = console.input("[bold green]> [/bold green]")

        if task.lower() in ("quit", "exit", "q"):
            console.print("[dim]Goodbye![/dim]")
            break

        if not task.strip():
            continue

        run_agent_loop(client, task, working_dir)


if __name__ == "__main__":
    main()
