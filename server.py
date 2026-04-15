from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
import uvicorn
#!/usr/bin/env python3
"""
ferretlog MCP server

Exposes ferretlog CLI commands as MCP tools.
"""

from fastmcp import FastMCP
import subprocess
import os
import re
from typing import Optional

mcp = FastMCP("ferretlog")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_escape.sub('', text)


def _run_ferretlog(*args: str) -> dict:
    """
    Run a ferretlog CLI command and return output.
    Returns a dict with 'output', 'error', and 'returncode'.
    """
    cmd = ["ferretlog"] + list(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        output = result.stdout
        error = result.stderr
        return {
            "output": output,
            "error": error,
            "returncode": result.returncode,
            "success": result.returncode == 0
        }
    except FileNotFoundError:
        return {
            "output": "",
            "error": "ferretlog CLI not found. Please install it with: pip install ferretlog",
            "returncode": -1,
            "success": False
        }
    except subprocess.TimeoutExpired:
        return {
            "output": "",
            "error": "ferretlog command timed out after 30 seconds",
            "returncode": -1,
            "success": False
        }
    except Exception as e:
        return {
            "output": "",
            "error": f"Unexpected error running ferretlog: {str(e)}",
            "returncode": -1,
            "success": False
        }


@mcp.tool()
async def list_runs(
    limit: Optional[int] = 20,
    no_color: Optional[bool] = False
) -> dict:
    """
    List recent Claude Code agent runs in git log style for the current project.
    Use this to get an overview of all agent sessions, their tasks, costs,
    token usage, and duration. Shows short IDs that can be used with other commands.

    Args:
        limit: Maximum number of runs to display. Defaults to 20.
        no_color: Disable colored output for plain text display.
    """
    args = []

    if limit and limit != 20:
        args += ["--limit", str(limit)]

    if no_color:
        args += ["--no-color"]

    result = _run_ferretlog(*args)

    if result["success"]:
        output = result["output"]
        if no_color:
            output = _strip_ansi(output)
        return {
            "runs": output,
            "success": True
        }
    else:
        return {
            "runs": "",
            "error": result["error"] or "Failed to list runs",
            "success": False
        }


@mcp.tool()
async def show_run(
    run_id: str,
    no_color: Optional[bool] = False
) -> dict:
    """
    Show a full tool-by-tool breakdown of a specific agent run.
    Use this when you need to understand exactly what an agent did during a
    session — which files it read, what commands it ran, and what edits it made.
    Requires a run ID from list_runs.

    Args:
        run_id: The short or full run ID (e.g. 'a3f2b1c9') obtained from list_runs.
        no_color: Disable colored output for plain text display.
    """
    if not run_id:
        return {
            "detail": "",
            "error": "run_id is required",
            "success": False
        }

    args = ["show", run_id]

    if no_color:
        args += ["--no-color"]

    result = _run_ferretlog(*args)

    if result["success"]:
        output = result["output"]
        if no_color:
            output = _strip_ansi(output)
        return {
            "detail": output,
            "run_id": run_id,
            "success": True
        }
    else:
        return {
            "detail": "",
            "run_id": run_id,
            "error": result["error"] or f"Failed to show run {run_id}",
            "success": False
        }


@mcp.tool()
async def diff_runs(
    run_id_a: str,
    run_id_b: str,
    no_color: Optional[bool] = False
) -> dict:
    """
    Compare two agent runs side-by-side to see how they differed in approach,
    tool usage, files touched, and outcomes. Use this to understand why the
    same or similar prompt produced different results across two sessions.

    Args:
        run_id_a: The short or full ID of the first run to compare (e.g. 'a3f2b1c9').
        run_id_b: The short or full ID of the second run to compare (e.g. '9c1b2d3e').
        no_color: Disable colored output for plain text display.
    """
    if not run_id_a:
        return {
            "comparison": "",
            "error": "run_id_a is required",
            "success": False
        }
    if not run_id_b:
        return {
            "comparison": "",
            "error": "run_id_b is required",
            "success": False
        }

    args = ["diff", run_id_a, run_id_b]

    if no_color:
        args += ["--no-color"]

    result = _run_ferretlog(*args)

    if result["success"]:
        output = result["output"]
        if no_color:
            output = _strip_ansi(output)
        return {
            "comparison": output,
            "run_id_a": run_id_a,
            "run_id_b": run_id_b,
            "success": True
        }
    else:
        return {
            "comparison": "",
            "run_id_a": run_id_a,
            "run_id_b": run_id_b,
            "error": result["error"] or f"Failed to diff runs {run_id_a} and {run_id_b}",
            "success": False
        }


@mcp.tool()
async def get_stats(
    no_color: Optional[bool] = False
) -> dict:
    """
    Show aggregate statistics across all agent runs for the current project,
    including total cost, total tokens consumed, total time spent, number of
    sessions, and per-model breakdowns. Use this to understand overall agent
    usage and spending.

    Args:
        no_color: Disable colored output for plain text display.
    """
    args = ["stats"]

    if no_color:
        args += ["--no-color"]

    result = _run_ferretlog(*args)

    if result["success"]:
        output = result["output"]
        if no_color:
            output = _strip_ansi(output)
        return {
            "stats": output,
            "success": True
        }
    else:
        return {
            "stats": "",
            "error": result["error"] or "Failed to get stats",
            "success": False
        }




async def health(request):
    return JSONResponse({"status": "ok", "server": mcp.name})

async def tools(request):
    registered = await mcp.list_tools()
    tool_list = [{"name": t.name, "description": t.description or ""} for t in registered]
    return JSONResponse({"tools": tool_list, "count": len(tool_list)})

mcp_app = mcp.http_app()

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
