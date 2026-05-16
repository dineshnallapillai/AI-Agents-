"""CLI entry point with argument parsing."""

import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Batch Code Agent — Claude Code-like agent (Bedrock or Anthropic Batch API)"
    )
    parser.add_argument(
        "--model",
        choices=["sonnet", "haiku", "opus"],
        default="sonnet",
        help="Model to use (default: sonnet)",
    )
    parser.add_argument(
        "--backend",
        choices=["bedrock", "anthropic"],
        default=None,
        help="Backend: 'bedrock' (AWS) or 'anthropic' (direct API + batch). Overrides config.",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="AWS region for Bedrock (default: from config)",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="AWS profile name for Bedrock credentials",
    )
    parser.add_argument(
        "--dir",
        default=os.getcwd(),
        help="Working directory (default: current directory)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=50,
        help="Max agentic loop turns (default: 50)",
    )
    parser.add_argument(
        "--task",
        type=str,
        default=None,
        help="Run a single task non-interactively and exit",
    )

    args = parser.parse_args()

    # Override config before importing agent
    import config

    config.MODEL_CHOICE = args.model
    config.MAX_TURNS = args.max_turns

    if args.backend:
        config.BACKEND = args.backend
    if args.region:
        config.AWS_REGION = args.region
    if args.profile:
        config.AWS_PROFILE = args.profile

    from agent import create_client, run_agent_loop, get_model_id, console
    from rich.panel import Panel

    working_dir = os.path.abspath(args.dir)

    console.print(
        Panel(
            "[bold]Batch Code Agent[/bold]\n"
            f"Backend: {config.BACKEND}\n"
            f"Model: {get_model_id()}\n"
            f"Working dir: {working_dir}\n\n"
            "[dim]Type your task, or 'quit' to exit.[/dim]",
            title="Batch Code Agent",
        )
    )

    client = create_client()

    if args.task:
        run_agent_loop(client, args.task, working_dir)
        return

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
