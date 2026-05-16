"""
Self-Evolving Agent
====================
An AI agent that starts with ZERO tools and creates its own on demand.

When it encounters a task it can't do, it:
  1. Writes a Python function to handle it
  2. Validates the code in a sandbox
  3. Registers it as a callable tool
  4. Executes it immediately
  5. Persists it for future sessions

Usage:
  python agent.py --provider claude
  python agent.py --provider ollama --model qwen3
"""

import os
import re
import sys
import json
import time
import importlib
import traceback
import argparse
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax

console = Console()

# ============================================================================
# TOOL REGISTRY — persistent, self-growing
# ============================================================================

TOOLS_DIR = os.path.join(os.path.dirname(__file__), "evolved_tools")
REGISTRY_FILE = os.path.join(TOOLS_DIR, "registry.json")

os.makedirs(TOOLS_DIR, exist_ok=True)


class ToolRegistry:
    def __init__(self):
        self.tools = {}
        self.metadata = {}
        self._load()

    def _load(self):
        if not os.path.exists(REGISTRY_FILE):
            return

        with open(REGISTRY_FILE, "r") as f:
            registry = json.load(f)

        for name, meta in registry.items():
            tool_file = os.path.join(TOOLS_DIR, f"{name}.py")
            if not os.path.exists(tool_file):
                continue

            try:
                fn = self._load_function(name, tool_file, meta["function_name"])
                self.tools[name] = fn
                self.metadata[name] = meta
            except Exception as e:
                console.print(f"[yellow]Failed to load tool '{name}': {e}[/yellow]")

    def _load_function(self, module_name, file_path, function_name):
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, function_name)

    def _save_registry(self):
        with open(REGISTRY_FILE, "w") as f:
            json.dump(self.metadata, f, indent=2)

    @staticmethod
    def _sanitize_code(code: str) -> str:
        replacements = {
            "\u2014": "--",   # em-dash
            "\u2013": "-",    # en-dash
            "\u2018": "'",    # left single quote
            "\u2019": "'",    # right single quote
            "\u201c": '"',    # left double quote
            "\u201d": '"',    # right double quote
            "\u2026": "...",  # ellipsis
            "\u2192": "->",   # right arrow
            "\u2190": "<-",   # left arrow
            "\u2265": ">=",   # >=
            "\u2264": "<=",   # <=
            "\u2260": "!=",   # !=
            "\u00d7": "*",    # multiplication sign
            "\u00f7": "/",    # division sign
            "\u2022": "-",    # bullet
            "\u00a0": " ",    # non-breaking space
            "\u200b": "",     # zero-width space
            "\u2011": "-",    # non-breaking hyphen
            "\u2012": "-",    # figure dash
            "\u00b7": "*",    # middle dot
            "\u2015": "--",   # horizontal bar
            "\u0097": "--",   # Windows em-dash (cp1252 0x97)
        }
        for char, replacement in replacements.items():
            code = code.replace(char, replacement)
        # Strip any remaining non-ASCII from comments/strings that would break encoding
        return code.encode("ascii", errors="replace").decode("ascii")

    def register(self, name: str, code: str, description: str, parameters: dict, function_name: str) -> str:
        tool_file = os.path.join(TOOLS_DIR, f"{name}.py")
        code = self._sanitize_code(code)

        # Validate by executing in isolated namespace
        try:
            namespace = {}
            exec(compile(code, tool_file, "exec"), namespace)
            if function_name not in namespace:
                return f"Error: function '{function_name}' not found in code"
            fn = namespace[function_name]
            if not callable(fn):
                return f"Error: '{function_name}' is not callable"
        except Exception as e:
            return f"Validation error: {e}"

        with open(tool_file, "w") as f:
            f.write(code)

        self.tools[name] = self._load_function(name, tool_file, function_name)
        self.metadata[name] = {
            "name": name,
            "description": description,
            "parameters": self._normalize_schema(parameters),
            "function_name": function_name,
            "created": datetime.now().isoformat(),
            "times_used": 0,
        }
        self._save_registry()
        return "success"

    def execute(self, name: str, arguments: dict) -> str:
        if name not in self.tools:
            return json.dumps({"error": f"Tool '{name}' not found"})

        try:
            result = self.tools[name](**arguments)
            self.metadata[name]["times_used"] = self.metadata[name].get("times_used", 0) + 1
            self._save_registry()
            if not isinstance(result, str):
                result = json.dumps(result, default=str)
            return result
        except Exception as e:
            return json.dumps({"error": str(e), "traceback": traceback.format_exc()})

    @staticmethod
    def _normalize_schema(params: dict) -> dict:
        if not params:
            return {"type": "object", "properties": {}}
        if params.get("type") == "object" and "properties" in params:
            return params
        return {"type": "object", "properties": params}

    def get_tool_definitions(self) -> list[dict]:
        defs = []
        for name, meta in self.metadata.items():
            schema = meta["parameters"]
            if not isinstance(schema, dict) or schema.get("type") != "object":
                schema = self._normalize_schema(schema)
            defs.append({
                "name": name,
                "description": meta["description"],
                "input_schema": schema,
            })
        return defs

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": name,
                "description": meta["description"],
                "created": meta["created"],
                "times_used": meta.get("times_used", 0),
            }
            for name, meta in self.metadata.items()
        ]

    def delete(self, name: str) -> bool:
        if name in self.tools:
            del self.tools[name]
        if name in self.metadata:
            del self.metadata[name]
        tool_file = os.path.join(TOOLS_DIR, f"{name}.py")
        if os.path.exists(tool_file):
            os.remove(tool_file)
        self._save_registry()
        return True

    def get_tool_source(self, name: str) -> str:
        tool_file = os.path.join(TOOLS_DIR, f"{name}.py")
        if os.path.exists(tool_file):
            return Path(tool_file).read_text()
        return ""


registry = ToolRegistry()


# ============================================================================
# META-TOOLS — the agent's built-in ability to create and manage tools
# ============================================================================

META_TOOLS = [
    {
        "name": "create_tool",
        "description": (
            "Create a new Python tool that the agent can use. Write the full Python code "
            "for a function that performs a specific task. The code will be validated, "
            "saved, and registered as a callable tool for current and future sessions. "
            "Include all necessary imports inside the function or at module level. "
            "The function must accept keyword arguments and return a string or JSON-serializable result."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "Snake_case name for the tool (e.g., fetch_weather, read_csv)",
                },
                "description": {
                    "type": "string",
                    "description": "What this tool does — shown to the LLM in future calls",
                },
                "function_name": {
                    "type": "string",
                    "description": "The Python function name in the code",
                },
                "parameters": {
                    "type": "object",
                    "description": "JSON Schema for the function parameters",
                },
                "code": {
                    "type": "string",
                    "description": "Full Python source code including imports and the function definition",
                },
            },
            "required": ["tool_name", "description", "function_name", "parameters", "code"],
        },
    },
    {
        "name": "list_tools",
        "description": "List all available tools the agent has created so far.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "view_tool_source",
        "description": "View the source code of a previously created tool.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "description": "Name of the tool to view"},
            },
            "required": ["tool_name"],
        },
    },
    {
        "name": "delete_tool",
        "description": "Delete a previously created tool.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "description": "Name of the tool to delete"},
            },
            "required": ["tool_name"],
        },
    },
    {
        "name": "fix_tool",
        "description": (
            "Fix a broken tool by providing updated code. Use this when a tool "
            "execution fails and you need to correct the implementation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "description": "Name of the tool to fix"},
                "code": {"type": "string", "description": "Corrected full Python source code"},
            },
            "required": ["tool_name", "code"],
        },
    },
]


def _check_required(arguments: dict, required: list[str], tool_name: str) -> str | None:
    missing = [k for k in required if k not in arguments]
    if missing:
        return json.dumps({"error": f"{tool_name} missing required arguments: {', '.join(missing)}"})
    return None


def execute_meta_tool(name: str, arguments: dict) -> str:
    if name == "create_tool":
        err = _check_required(arguments, ["tool_name", "description", "function_name", "parameters", "code"], name)
        if err:
            return err

        console.print(Panel(
            Syntax(arguments["code"], "python", theme="monokai"),
            title=f"[bold green]Creating tool: {arguments['tool_name']}[/bold green]",
            border_style="green",
        ))

        result = registry.register(
            name=arguments["tool_name"],
            code=arguments["code"],
            description=arguments["description"],
            parameters=arguments["parameters"],
            function_name=arguments["function_name"],
        )

        if result == "success":
            console.print(f"[bold green]+ Tool '{arguments['tool_name']}' created and registered[/bold green]")
            return json.dumps({
                "status": "success",
                "tool_name": arguments["tool_name"],
                "message": f"Tool '{arguments['tool_name']}' is now available. You can call it directly.",
            })
        else:
            console.print(f"[bold red]x {result}[/bold red]")
            return json.dumps({"status": "error", "message": result})

    elif name == "list_tools":
        tools = registry.list_tools()
        return json.dumps({"tools": tools, "total": len(tools)})

    elif name == "view_tool_source":
        err = _check_required(arguments, ["tool_name"], name)
        if err:
            return err
        source = registry.get_tool_source(arguments["tool_name"])
        if source:
            return json.dumps({"tool_name": arguments["tool_name"], "source": source})
        return json.dumps({"error": f"Tool '{arguments['tool_name']}' not found"})

    elif name == "delete_tool":
        err = _check_required(arguments, ["tool_name"], name)
        if err:
            return err
        registry.delete(arguments["tool_name"])
        return json.dumps({"status": "deleted", "tool_name": arguments["tool_name"]})

    elif name == "fix_tool":
        err = _check_required(arguments, ["tool_name", "code"], name)
        if err:
            return err

        arguments["code"] = ToolRegistry._sanitize_code(arguments["code"])

        meta = registry.metadata.get(arguments["tool_name"])
        if not meta:
            return json.dumps({"error": f"Tool '{arguments['tool_name']}' not found"})

        console.print(Panel(
            Syntax(arguments["code"], "python", theme="monokai"),
            title=f"[bold yellow]Fixing tool: {arguments['tool_name']}[/bold yellow]",
            border_style="yellow",
        ))

        result = registry.register(
            name=arguments["tool_name"],
            code=arguments["code"],
            description=meta["description"],
            parameters=meta["parameters"],
            function_name=meta["function_name"],
        )

        if result == "success":
            console.print(f"[bold green]+ Tool '{arguments['tool_name']}' fixed[/bold green]")
            return json.dumps({"status": "fixed", "tool_name": arguments["tool_name"]})
        return json.dumps({"status": "error", "message": result})

    return json.dumps({"error": f"Unknown meta-tool: {name}"})


# ============================================================================
# SYSTEM PROMPT
# ============================================================================

SYSTEM_PROMPT = """You are a Self-Evolving Agent. You start with NO pre-built tools except the ability to CREATE new tools.

YOUR CORE ABILITY:
When a user asks you to do something you can't do yet, you MUST:
1. Think about what Python function would solve this
2. Use create_tool to write and register that function
3. Immediately call your newly created tool
4. Return the result to the user

RULES:
- ALWAYS create a tool when you need a capability you don't have
- Write clean, working Python code with all imports inside the code
- Handle errors gracefully in your tool code
- If a tool fails, use fix_tool to correct it — don't give up
- Reuse existing tools when they fit — check list_tools first
- Each tool should do ONE thing well
- Tools persist across sessions — they are your growing skill set

TOOL CODE GUIDELINES:
- Include all imports at the top of the code (not inside functions unless needed)
- Functions must accept keyword arguments matching the parameters schema
- Functions must return a string or JSON-serializable object
- Use standard library when possible; for external packages, handle ImportError gracefully
- Never use input() or any interactive prompts in tool code

SCORING AND RANKING GUIDELINES:
When creating tools that score, rank, or filter data, follow these rules strictly:
- Negative values (negative growth, negative returns, losses) must REDUCE the score, never increase it
- Validate that your scoring formula produces sensible results: the top-ranked items should have the BEST metrics, not the worst
- Use normalization (0-1 range) when combining metrics of different scales
- Before returning results, sanity-check: if the top result has mostly negative metrics, the scoring logic is wrong
- For financial/stock screeners: higher growth, lower P/E, positive analyst targets = better score

OUTPUT VALIDATION:
After a tool returns results, review the output before presenting it to the user:
- If the results look wrong (e.g., top-ranked items have bad metrics), acknowledge it and use fix_tool to correct the scoring logic
- If the tool errors, use fix_tool instead of giving up
- Always explain what the tool found and flag any caveats

You are building yourself. Every tool you create makes you more capable."""


# ============================================================================
# OUTPUT VALIDATION — catch bad scoring, nonsensical rankings, errors
# ============================================================================


def _validate_tool_output(tool_name: str, tool_input: dict, result: str) -> str | None:
    try:
        data = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return None

    if isinstance(data, dict) and "error" in data:
        return f"Tool '{tool_name}' returned an error: {data['error']}. Consider using fix_tool to correct it."

    if isinstance(data, dict) and "traceback" in data:
        return f"Tool '{tool_name}' crashed. Use fix_tool to correct the implementation."

    warnings = []

    items = None
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("results", "stocks", "items", "rankings", "data", "picks"):
            if isinstance(data.get(key), list) and len(data[key]) > 0:
                items = data[key]
                break

    if items and len(items) >= 2 and isinstance(items[0], dict):
        negative_fields = ["growth", "revenue_growth", "earnings_growth", "return", "upside", "score"]
        top_item = items[0]
        negative_count = 0
        checked = 0
        for field in negative_fields:
            for key in top_item:
                if field in key.lower():
                    val = top_item[key]
                    if isinstance(val, (int, float)) and val < 0:
                        negative_count += 1
                    elif isinstance(val, str):
                        cleaned = val.replace("%", "").replace("$", "").replace(",", "").strip()
                        try:
                            if float(cleaned) < 0:
                                negative_count += 1
                        except ValueError:
                            pass
                    checked += 1

        if checked > 0 and negative_count > checked * 0.5:
            warnings.append(
                f"The top-ranked result has negative values in {negative_count}/{checked} key metrics. "
                "The scoring logic is likely inverted — negative metrics should REDUCE the score, not increase it. "
                "Use fix_tool to correct the scoring formula."
            )

    return " | ".join(warnings) if warnings else None


# ============================================================================
# LLM PROVIDERS
# ============================================================================

BEDROCK_APP_PROFILE_ARN = "arn:aws:bedrock:eu-west-1:905121132271:application-inference-profile/g0nbe6qp4i3t"


class ClaudeProvider:
    def __init__(self, model="claude-sonnet-4-6", use_bedrock=True, aws_profile=None, aws_region=None):
        import anthropic
        self.model = model
        self._is_bedrock = False

        if use_bedrock:
            import boto3
            profile = aws_profile or os.environ.get("AWS_PROFILE", "claude-code-sso-profile")
            region = aws_region or os.environ.get("AWS_REGION", "eu-west-1")

            session = boto3.Session(profile_name=profile, region_name=region)
            credentials = session.get_credentials().get_frozen_credentials()

            self.client = anthropic.AnthropicBedrock(
                aws_access_key=credentials.access_key,
                aws_secret_key=credentials.secret_key,
                aws_session_token=credentials.token,
                aws_region=region,
            )
            self._is_bedrock = True
            self._provider_type = f"Bedrock/{region}"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            self.client = anthropic.Anthropic()
            self._provider_type = "API"
        else:
            raise ValueError("No auth found.")

    def _get_model_id(self):
        if self._is_bedrock:
            if self.model.startswith("arn:"):
                return self.model
            return BEDROCK_APP_PROFILE_ARN
        return self.model

    def chat(self, messages: list, tools: list, max_iterations: int = 30) -> str:
        model_id = self._get_model_id()

        for iteration in range(max_iterations):
            console.print(f"  [dim]--- iteration {iteration + 1}/{max_iterations} ---[/dim]")

            response = self.client.messages.create(
                model=model_id,
                max_tokens=4096,
                system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                tools=tools,
                messages=messages,
            )

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                return "\n".join(b.text for b in response.content if hasattr(b, "text"))

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input

                    meta_tool_names = {t["name"] for t in META_TOOLS}
                    if tool_name in meta_tool_names:
                        console.print(f"  [dim cyan]> meta: {tool_name}[/dim cyan]")
                        result = execute_meta_tool(tool_name, tool_input)
                    else:
                        console.print(f"  [dim green]> using: {tool_name}({json.dumps(tool_input)[:80]})[/dim green]")
                        result = registry.execute(tool_name, tool_input)
                        validation = _validate_tool_output(tool_name, tool_input, result)
                        if validation:
                            result += f"\n\n[VALIDATION WARNING]: {validation}"
                            console.print(f"  [dim yellow]> validation: {validation[:80]}[/dim yellow]")

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "user", "content": tool_results})

            tools = META_TOOLS + registry.get_tool_definitions()

            if iteration == max_iterations - 2:
                tool_results[-1]["content"] += "\n\nWARNING: You are on your last iteration. Provide your best answer NOW with whatever results you have."

        return "Agent reached maximum iterations."

    @property
    def display_name(self):
        return f"Claude ({self.model}) via {self._provider_type}"


class OllamaProvider:
    def __init__(self, model="qwen3"):
        import ollama as _ollama
        self.ollama = _ollama
        self.model = model

    def _to_ollama_tools(self, tools):
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]

    def chat(self, messages: list, tools: list, max_iterations: int = 30) -> str:
        ollama_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in messages:
            if msg["role"] == "user":
                if isinstance(msg["content"], str):
                    ollama_messages.append(msg)
                elif isinstance(msg["content"], list):
                    for item in msg["content"]:
                        if isinstance(item, dict) and item.get("type") == "tool_result":
                            ollama_messages.append({"role": "tool", "content": item["content"]})
            elif msg["role"] == "assistant":
                if isinstance(msg["content"], str):
                    ollama_messages.append(msg)

        for iteration in range(max_iterations):
            console.print(f"  [dim]--- iteration {iteration + 1}/{max_iterations} ---[/dim]")

            ollama_tools = self._to_ollama_tools(tools)
            response = self.ollama.chat(
                model=self.model,
                messages=ollama_messages,
                tools=ollama_tools,
            )

            msg = response["message"]
            ollama_messages.append(msg)

            if not msg.get("tool_calls"):
                answer = msg.get("content", "")
                messages.append({"role": "assistant", "content": answer})
                return answer

            for tool_call in msg["tool_calls"]:
                fn_name = tool_call["function"]["name"]
                fn_args = tool_call["function"]["arguments"]

                meta_tool_names = {t["name"] for t in META_TOOLS}
                if fn_name in meta_tool_names:
                    console.print(f"  [dim cyan]> meta: {fn_name}[/dim cyan]")
                    result = execute_meta_tool(fn_name, fn_args)
                else:
                    console.print(f"  [dim green]> using: {fn_name}({json.dumps(fn_args)[:80]})[/dim green]")
                    result = registry.execute(fn_name, fn_args)
                    validation = _validate_tool_output(fn_name, fn_args, result)
                    if validation:
                        result += f"\n\n[VALIDATION WARNING]: {validation}"
                        console.print(f"  [dim yellow]> validation: {validation[:80]}[/dim yellow]")

                ollama_messages.append({"role": "tool", "content": result})

            tools = META_TOOLS + registry.get_tool_definitions()

            if iteration == max_iterations - 2:
                ollama_messages.append({"role": "system", "content": "WARNING: You are on your last iteration. Provide your best answer NOW with whatever results you have."})

        messages.append({"role": "assistant", "content": "Agent reached maximum iterations."})
        return "Agent reached maximum iterations."

    @property
    def display_name(self):
        return f"Ollama ({self.model})"


# ============================================================================
# CLI
# ============================================================================


def print_welcome(provider):
    n_tools = len(registry.list_tools())
    tool_status = f"[green]{n_tools} evolved tools loaded[/green]" if n_tools > 0 else "[yellow]No tools yet — I'll create them as needed[/yellow]"

    console.print(Panel.fit(
        f"[bold cyan]Self-Evolving Agent[/bold cyan]\n"
        f"[dim]Provider: {provider.display_name}[/dim]\n"
        f"Tools: {tool_status}\n\n"
        "I start with zero capabilities and build my own tools on demand.\n"
        "Ask me to do anything — I'll create the tools I need.\n\n"
        "[dim]Commands:[/dim]\n"
        "  [green]Just type[/green]       — Ask anything, I'll evolve to handle it\n"
        "  [green]/tools[/green]          — List all evolved tools\n"
        "  [green]/source name[/green]    — View a tool's source code\n"
        "  [green]/delete name[/green]    — Delete a tool\n"
        "  [green]/reset[/green]          — Delete all evolved tools\n"
        "  [green]/clear[/green]          — Clear conversation\n"
        "  [green]/quit[/green]           — Exit",
        border_style="cyan",
    ))


def show_tools():
    tools = registry.list_tools()
    if not tools:
        console.print("[yellow]No tools created yet. Ask me to do something![/yellow]")
        return

    table = Table(title=f"Evolved Tools ({len(tools)})")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="dim")
    table.add_column("Created", style="green")
    table.add_column("Used", style="yellow", justify="right")

    for t in tools:
        created = t["created"][:10] if t.get("created") else "?"
        table.add_row(t["name"], t["description"][:60], created, str(t.get("times_used", 0)))

    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Self-Evolving Agent")
    parser.add_argument("--provider", choices=["claude", "ollama"], default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--aws-profile", default=None)
    parser.add_argument("--aws-region", default=None)
    parser.add_argument("--no-bedrock", action="store_true")
    args = parser.parse_args()

    provider = None

    if args.provider == "claude":
        try:
            provider = ClaudeProvider(
                model=args.model or "claude-sonnet-4-6",
                use_bedrock=not args.no_bedrock,
                aws_profile=args.aws_profile,
                aws_region=args.aws_region,
            )
        except Exception as e:
            console.print(f"[red]Claude init failed: {e}[/red]")
            return
    elif args.provider == "ollama":
        model = args.model or "qwen3"
        try:
            import ollama as _ollama
            _ollama.show(model)
            provider = OllamaProvider(model=model)
        except Exception:
            console.print(f"[red]Ollama model '{model}' not found. Run: ollama pull {model}[/red]")
            return
    else:
        try:
            provider = ClaudeProvider(use_bedrock=True)
        except Exception:
            pass
        if not provider:
            try:
                import ollama as _ollama
                _ollama.list()
                provider = OllamaProvider()
            except Exception:
                console.print("[red]No provider available.[/red]")
                return

    print_welcome(provider)
    conversation = []

    while True:
        try:
            user_input = console.input("\n[bold green]You:[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        if user_input.lower() == "/quit":
            console.print("[dim]Goodbye![/dim]")
            break

        if user_input.lower() == "/clear":
            conversation.clear()
            console.print("[dim]Conversation cleared. Tools preserved.[/dim]")
            continue

        if user_input.lower() == "/tools":
            show_tools()
            continue

        if user_input.lower().startswith("/source "):
            name = user_input[8:].strip()
            source = registry.get_tool_source(name)
            if source:
                console.print(Panel(
                    Syntax(source, "python", theme="monokai"),
                    title=f"[cyan]{name}[/cyan]",
                    border_style="cyan",
                ))
            else:
                console.print(f"[red]Tool '{name}' not found[/red]")
            continue

        if user_input.lower().startswith("/delete "):
            name = user_input[8:].strip()
            registry.delete(name)
            console.print(f"[green]Tool '{name}' deleted[/green]")
            continue

        if user_input.lower() == "/reset":
            for t in list(registry.metadata.keys()):
                registry.delete(t)
            console.print("[green]All tools deleted. Starting fresh.[/green]")
            continue

        console.print()
        try:
            # Keep conversation manageable — trim old turns but keep last 20
            if len(conversation) > 40:
                conversation[:] = conversation[-20:]

            conversation.append({"role": "user", "content": user_input})
            tools = META_TOOLS + registry.get_tool_definitions()
            response = provider.chat(conversation, tools)
            console.print(Panel(Markdown(response), border_style="blue", title=provider.display_name))
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    main()
