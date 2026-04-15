#!/usr/bin/env python3
"""
ferretlog MCP Server
Provides tools to inspect Claude Code agent run logs via ferretlog CLI.
"""

import os
import subprocess
import json
from typing import Optional
from fastmcp import FastMCP

mcp = FastMCP("ferretlog")


def _run_ferretlog(*args: str, cwd: Optional[str] = None) -> str:
    """Run the ferretlog CLI with given arguments and return output."""
    cmd = ["ferretlog"] + list(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd or os.getcwd(),
            timeout=30,
        )
        output = result.stdout
        if result.returncode != 0 and result.stderr:
            output += "\n" + result.stderr
        return output.strip() if output.strip() else "No output returned."
    except FileNotFoundError:
        return (
            "Error: 'ferretlog' CLI not found. "
            "Please install it with: pip install ferretlog"
        )
    except subprocess.TimeoutExpired:
        return "Error: ferretlog command timed out after 30 seconds."
    except Exception as e:
        return f"Error running ferretlog: {str(e)}"


@mcp.tool()
async def list_runs(
    limit: Optional[int] = 20,
    project_path: Optional[str] = None,
) -> dict:
    """
    List recent Claude Code agent runs in git log style.
    Use this as the default starting point to get an overview of recent agent
    sessions, their tasks, cost, duration, and token usage.
    Shows a summary table of all runs for the current project.
    """
    args = []
    if limit is not None and limit != 20:
        args.extend(["--limit", str(limit)])

    cwd = project_path if project_path else None
    output = _run_ferretlog(*args, cwd=cwd)

    return {
        "tool": "list_runs",
        "limit": limit,
        "project_path": project_path or os.getcwd(),
        "output": output,
    }


@mcp.tool()
async def show_run(run_id: str) -> dict:
    """
    Show a full tool-by-tool breakdown of a specific agent run.
    Use this when you want to replay or inspect exactly what the agent did in a
    session: which files it read, what commands it ran, what edits it made,
    along with token counts, cost, and duration.
    """
    if not run_id or not run_id.strip():
        return {
            "error": "run_id is required. Obtain a run ID from list_runs first."
        }

    output = _run_ferretlog("show", run_id.strip())

    return {
        "tool": "show_run",
        "run_id": run_id.strip(),
        "output": output,
    }


@mcp.tool()
async def diff_runs(run_id_a: str, run_id_b: str) -> dict:
    """
    Side-by-side comparison of two agent runs.
    Use this when you want to understand why the same or similar prompt produced
    different results, or to compare tool call sequences, files touched, and
    costs between two sessions.
    """
    if not run_id_a or not run_id_a.strip():
        return {"error": "run_id_a is required."}
    if not run_id_b or not run_id_b.strip():
        return {"error": "run_id_b is required."}

    output = _run_ferretlog("diff", run_id_a.strip(), run_id_b.strip())

    return {
        "tool": "diff_runs",
        "run_id_a": run_id_a.strip(),
        "run_id_b": run_id_b.strip(),
        "output": output,
    }


@mcp.tool()
async def get_stats(project_path: Optional[str] = None) -> dict:
    """
    Show aggregate statistics across all Claude Code agent runs for the current
    project. Use this to understand total cost, token usage, average session
    duration, most-used models, and overall usage patterns over time.
    """
    cwd = project_path if project_path else None
    output = _run_ferretlog("stats", cwd=cwd)

    return {
        "tool": "get_stats",
        "project_path": project_path or os.getcwd(),
        "output": output,
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))))
