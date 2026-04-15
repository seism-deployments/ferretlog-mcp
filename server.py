from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
import uvicorn
#!/usr/bin/env python3
"""
FastMCP server for ferretlog 🐾
Provides tools to inspect Claude Code agent run logs.
"""

from fastmcp import FastMCP
import subprocess
import os
import sys
from typing import Optional

mcp = FastMCP("ferretlog")


def _run_ferretlog(args: list[str], no_color: bool = False) -> str:
    """Run the ferretlog CLI with given arguments and return output."""
    cmd = [sys.executable, "-m", "ferretlog"] + args
    # Try direct ferretlog command first, fall back to python -m
    env = os.environ.copy()
    if no_color:
        env["NO_COLOR"] = "1"
        env["TERM"] = "dumb"
    
    # Try running as a module first
    try:
        result = subprocess.run(
            ["ferretlog"] + args,
            capture_output=True,
            text=True,
            env=env,
            timeout=30
        )
        if result.returncode == 0 or result.stdout:
            return result.stdout + (result.stderr if result.stderr else "")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fall back to python -m ferretlog
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ferretlog"] + args,
            capture_output=True,
            text=True,
            env=env,
            timeout=30
        )
        return result.stdout + (result.stderr if result.stderr else "")
    except Exception as e:
        return f"Error running ferretlog: {str(e)}"


def _strip_ansi(text: str) -> str:
    """Strip ANSI escape codes from text."""
    import re
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


@mcp.tool()
def list_runs(
    limit: Optional[int] = 20,
    no_color: Optional[bool] = False
) -> dict:
    """
    List all Claude Code agent runs in the current repository, git-log style.
    Use this to get an overview of recent agent sessions, their costs, duration,
    and what task was performed. Shows run IDs needed for other commands.
    """
    args = []
    if limit and limit != 20:
        args.extend(["--limit", str(limit)])

    output = _run_ferretlog(args, no_color=no_color or False)

    if no_color:
        output = _strip_ansi(output)

    return {
        "output": output,
        "limit": limit,
        "tool": "list_runs"
    }


@mcp.tool()
def show_run(
    run_id: str,
    no_color: Optional[bool] = False
) -> dict:
    """
    Show a full tool-by-tool breakdown of a specific Claude Code agent run.
    Use this when you want to understand exactly what the agent did during a
    session: which files it read, what bash commands it ran, what edits it made,
    tokens used, and cost. Requires a run ID from list_runs.
    """
    args = ["show", run_id]
    output = _run_ferretlog(args, no_color=no_color or False)

    if no_color:
        output = _strip_ansi(output)

    return {
        "output": output,
        "run_id": run_id,
        "tool": "show_run"
    }


@mcp.tool()
def diff_runs(
    run_id_a: str,
    run_id_b: str,
    no_color: Optional[bool] = False
) -> dict:
    """
    Side-by-side comparison of two Claude Code agent runs.
    Use this to understand why the same or similar prompt produced different
    results, to compare tool call sequences, file touches, token usage, and
    costs between two sessions.
    """
    args = ["diff", run_id_a, run_id_b]
    output = _run_ferretlog(args, no_color=no_color or False)

    if no_color:
        output = _strip_ansi(output)

    return {
        "output": output,
        "run_id_a": run_id_a,
        "run_id_b": run_id_b,
        "tool": "diff_runs"
    }


@mcp.tool()
def get_stats(
    no_color: Optional[bool] = False
) -> dict:
    """
    Show aggregate statistics across all Claude Code agent runs.
    Includes total cost, total tokens consumed, total time spent, number of
    sessions, most-used models, and most-touched files. Use this for a
    high-level summary of overall agent usage and spend.
    """
    args = ["stats"]
    output = _run_ferretlog(args, no_color=no_color or False)

    if no_color:
        output = _strip_ansi(output)

    return {
        "output": output,
        "tool": "get_stats"
    }




async def health(request):
    return JSONResponse({"status": "ok", "server": mcp.name})

async def tools(request):
    registered = await mcp.list_tools()
    tool_list = [{"name": t.name, "description": t.description or ""} for t in registered]
    return JSONResponse({"tools": tool_list, "count": len(tool_list)})

mcp_app = mcp.http_app(transport="streamable-http")

app = Starlette(
    routes=[
        Route("/health", health),
        Route("/tools", tools),
        Mount("/", mcp_app),
    ],
    lifespan=mcp_app.lifespan,
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
