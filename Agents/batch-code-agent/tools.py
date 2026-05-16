"""Tool definitions and execution for the batch code agent."""

import os
import subprocess
import glob as glob_module
import re
from pathlib import Path


TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file at the given path. Returns the file content with line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file to read",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start reading from (0-indexed). Optional.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of lines to read. Optional.",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file, creating it if it doesn't exist or overwriting if it does.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file",
                },
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Replace a specific string in a file with a new string. The old_string must be unique in the file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact string to find and replace (must be unique in file)",
                },
                "new_string": {
                    "type": "string",
                    "description": "The string to replace it with",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        },
    },
    {
        "name": "bash",
        "description": "Execute a bash command and return its stdout and stderr. Use for running tests, git commands, builds, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds. Default 60.",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "glob_search",
        "description": "Find files matching a glob pattern. Returns list of matching file paths.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g., '**/*.py', 'src/**/*.ts')",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in. Defaults to current working directory.",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "grep_search",
        "description": "Search for a regex pattern in files. Returns matching lines with file paths and line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search in. Defaults to current directory.",
                },
                "include": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g., '*.py'). Optional.",
                },
            },
            "required": ["pattern"],
        },
    },
]


def execute_tool(tool_name: str, tool_input: dict, working_dir: str) -> str:
    """Execute a tool and return the result as a string."""
    try:
        if tool_name == "read_file":
            return _read_file(tool_input, working_dir)
        elif tool_name == "write_file":
            return _write_file(tool_input, working_dir)
        elif tool_name == "edit_file":
            return _edit_file(tool_input, working_dir)
        elif tool_name == "bash":
            return _bash(tool_input, working_dir)
        elif tool_name == "glob_search":
            return _glob_search(tool_input, working_dir)
        elif tool_name == "grep_search":
            return _grep_search(tool_input, working_dir)
        else:
            return f"Error: Unknown tool '{tool_name}'"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


def _resolve_path(file_path: str, working_dir: str) -> str:
    if os.path.isabs(file_path):
        return file_path
    return os.path.join(working_dir, file_path)


def _read_file(tool_input: dict, working_dir: str) -> str:
    path = _resolve_path(tool_input["file_path"], working_dir)
    if not os.path.exists(path):
        return f"Error: File not found: {path}"
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    offset = tool_input.get("offset", 0)
    limit = tool_input.get("limit", len(lines))
    selected = lines[offset : offset + limit]
    numbered = [f"{i + offset + 1}\t{line}" for i, line in enumerate(selected)]
    return "".join(numbered) if numbered else "(empty file)"


def _write_file(tool_input: dict, working_dir: str) -> str:
    path = _resolve_path(tool_input["file_path"], working_dir)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(tool_input["content"])
    return f"Successfully wrote to {path}"


def _edit_file(tool_input: dict, working_dir: str) -> str:
    path = _resolve_path(tool_input["file_path"], working_dir)
    if not os.path.exists(path):
        return f"Error: File not found: {path}"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    old_string = tool_input["old_string"]
    new_string = tool_input["new_string"]
    count = content.count(old_string)
    if count == 0:
        return f"Error: old_string not found in {path}"
    if count > 1:
        return f"Error: old_string found {count} times in {path}. Must be unique."
    content = content.replace(old_string, new_string, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Successfully edited {path}"


def _bash(tool_input: dict, working_dir: str) -> str:
    command = tool_input["command"]
    timeout = tool_input.get("timeout", 60)
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=working_dir,
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n(exit code: {result.returncode})"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"


def _glob_search(tool_input: dict, working_dir: str) -> str:
    pattern = tool_input["pattern"]
    search_path = tool_input.get("path", working_dir)
    if not os.path.isabs(search_path):
        search_path = os.path.join(working_dir, search_path)
    full_pattern = os.path.join(search_path, pattern)
    matches = sorted(glob_module.glob(full_pattern, recursive=True))
    if not matches:
        return "No files found matching pattern."
    # Limit to 100 results
    if len(matches) > 100:
        return "\n".join(matches[:100]) + f"\n... and {len(matches) - 100} more"
    return "\n".join(matches)


def _grep_search(tool_input: dict, working_dir: str) -> str:
    pattern = tool_input["pattern"]
    search_path = tool_input.get("path", working_dir)
    if not os.path.isabs(search_path):
        search_path = os.path.join(working_dir, search_path)
    include = tool_input.get("include", "")

    cmd = ["grep", "-rn", "--color=never"]
    if include:
        cmd.extend(["--include", include])
    cmd.extend([pattern, search_path])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, cwd=working_dir
        )
        output = result.stdout.strip()
        if not output:
            return "No matches found."
        lines = output.split("\n")
        if len(lines) > 50:
            return "\n".join(lines[:50]) + f"\n... and {len(lines) - 50} more matches"
        return output
    except subprocess.TimeoutExpired:
        return "Error: Search timed out"
    except FileNotFoundError:
        # grep not available, fallback to Python
        return _grep_python_fallback(pattern, search_path, include)


def _grep_python_fallback(pattern: str, search_path: str, include: str) -> str:
    """Fallback grep using Python when system grep isn't available."""
    regex = re.compile(pattern)
    results = []
    search = Path(search_path)

    if search.is_file():
        files = [search]
    else:
        glob_pat = include if include else "**/*"
        files = list(search.glob(glob_pat))

    for fpath in files[:500]:
        if not fpath.is_file():
            continue
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f, 1):
                    if regex.search(line):
                        results.append(f"{fpath}:{i}:{line.rstrip()}")
                        if len(results) >= 50:
                            return "\n".join(results) + "\n... (truncated)"
        except (PermissionError, OSError):
            continue

    return "\n".join(results) if results else "No matches found."
