from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
import uvicorn
#!/usr/bin/env python3
"""
ferretlog MCP server — exposes ferretlog CLI functionality as MCP tools.
"""

from fastmcp import FastMCP
import subprocess
import os
import sys
from typing import Optional

mcp = FastMCP("ferretlog")


def _run_ferretlog(*args: str, no_color: bool = False) -> str:
    """Run a ferretlog CLI command and return stdout+stderr as a string."""
    cmd = [sys.executable, "-m", "ferretlog"] if False else ["ferretlog"]
    # Try ferretlog directly, fall back to python -m ferretlog
    full_args = list(args)
    if no_color:
        full_args.append("--no-color")

    env = os.environ.copy()
    if no_color:
        env["NO_COLOR"] = "1"

    # Attempt 1: ferretlog as installed CLI
    try:
        result = subprocess.run(
            ["ferretlog"] + full_args,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        return output.strip()
    except FileNotFoundError:
        pass

    # Attempt 2: python -m ferretlog
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ferretlog"] + full_args,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        return output.strip()
    except Exception as e:
        return f"Error running ferretlog: {e}"


@mcp.tool()
def list_runs(
    limit: int = 20,
    no_color: bool = False,
) -> dict:
    """
    List recent Claude Code agent runs in git log style for the current project.
    Use this to get an overview of recent agent sessions, their tasks, costs,
    token usage, duration, and file changes. Shows short IDs that can be used
    with other commands.
    """
    args = []
    if limit != 20:
        args += ["--limit", str(limit)]

    output = _run_ferretlog(*args, no_color=no_color)
    return {
        "output": output,
        "limit": limit,
    }


@mcp.tool()
def show_run(
    run_id: str,
    no_color: bool = False,
) -> dict:
    """
    Show a full tool-by-tool breakdown of a specific agent run.
    Use this when you need to understand exactly what an agent did during a
    session — which files it read, edited, bash commands it ran, and in what
    order. Requires a run ID from list_runs.
    """
    output = _run_ferretlog("show", run_id, no_color=no_color)
    return {
        "run_id": run_id,
        "output": output,
    }


@mcp.tool()
def diff_runs(
    run_id_a: str,
    run_id_b: str,
    no_color: bool = False,
) -> dict:
    """
    Compare two agent runs side by side to understand why the same or similar
    prompt led to different behavior. Use this to debug inconsistent agent
    behavior, compare approaches across sessions, or understand regressions.
    """
    output = _run_ferretlog("diff", run_id_a, run_id_b, no_color=no_color)
    return {
        "run_id_a": run_id_a,
        "run_id_b": run_id_b,
        "output": output,
    }


@mcp.tool()
def get_stats(
    no_color: bool = False,
) -> dict:
    """
    Show aggregate statistics across all Claude Code agent sessions — total
    cost, token usage, time spent, number of runs, and breakdowns by model.
    Use this for cost tracking, productivity reporting, or understanding
    overall agent usage patterns.
    """
    output = _run_ferretlog("stats", no_color=no_color)
    return {
        "output": output,
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
