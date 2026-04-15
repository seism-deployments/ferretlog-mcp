#!/usr/bin/env python3
"""
Ferretlog MCP Server
Provides tools to inspect Claude Code agent run logs via ferretlog CLI.
"""

import asyncio
import subprocess
import sys
from typing import Optional

from fastmcp import FastMCP

mcp = FastMCP("ferretlog")


async def _run_ferretlog(*args: str) -> str:
    """Run the ferretlog CLI with the given arguments and return stdout."""
    cmd = [sys.executable, "-m", "ferretlog"] 
    # Try ferretlog directly first
    try:
        proc = await asyncio.create_subprocess_exec(
            "ferretlog", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            return stdout.decode("utf-8", errors="replace")
        # If ferretlog not found, fall through to python -m
        err_text = stderr.decode("utf-8", errors="replace")
        if proc.returncode != 0 and "not found" not in err_text.lower() and "No such file" not in err_text:
            return f"Error running ferretlog: {err_text}\n{stdout.decode('utf-8', errors='replace')}"
    except FileNotFoundError:
        pass

    # Fallback: try python -m ferretlog
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "ferretlog", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace")
        err_text = stderr.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            return f"Error running ferretlog: {err_text}\n{output}"
        return output
    except FileNotFoundError:
        return "Error: ferretlog is not installed. Install it with: pip install ferretlog"


@mcp.tool()
async def list_runs(
    limit: Optional[int] = 20,
    no_color: Optional[bool] = False,
) -> str:
    """
    List recent Claude Code agent runs in git-log style for the current project.
    Use this to get an overview of past agent sessions, their tasks, costs,
    token usage, duration, and short IDs. Call this first to discover available
    run IDs before using show_run, diff_runs, or get_stats.
    """
    args = []

    if limit is not None and limit != 20:
        args.extend(["--limit", str(limit)])

    if no_color:
        args.append("--no-color")

    result = await _run_ferretlog(*args)
    return result


@mcp.tool()
async def show_run(
    run_id: str,
    no_color: Optional[bool] = False,
) -> str:
    """
    Display the full tool-by-tool breakdown of a specific agent run, including
    every file read/edited, every bash command executed, token counts, cost,
    duration, model, and branch. Use this when you want to replay or audit
    exactly what the agent did in a particular session. Requires a run ID
    from list_runs.
    """
    if not run_id or not run_id.strip():
        return "Error: run_id is required. Use list_runs first to get a valid run ID."

    args = ["show", run_id.strip()]

    if no_color:
        args.append("--no-color")

    result = await _run_ferretlog(*args)
    return result


@mcp.tool()
async def diff_runs(
    run_id_a: str,
    run_id_b: str,
    no_color: Optional[bool] = False,
) -> str:
    """
    Compare two agent runs side-by-side to see how they differed in approach,
    tool calls, files touched, cost, and duration. Use this when the same task
    was attempted multiple times and you want to understand why the outcomes
    differed, or to compare efficiency between runs.
    """
    if not run_id_a or not run_id_a.strip():
        return "Error: run_id_a is required."
    if not run_id_b or not run_id_b.strip():
        return "Error: run_id_b is required."

    args = ["diff", run_id_a.strip(), run_id_b.strip()]

    if no_color:
        args.append("--no-color")

    result = await _run_ferretlog(*args)
    return result


@mcp.tool()
async def get_stats(
    no_color: Optional[bool] = False,
) -> str:
    """
    Show aggregate statistics across all Claude Code agent runs for the current
    project, including total cost, total tokens consumed, total time spent,
    number of sessions, average session length, and per-model breakdowns.
    Use this to understand overall agent usage, spending trends, and efficiency
    at a glance.
    """
    args = ["stats"]

    if no_color:
        args.append("--no-color")

    result = await _run_ferretlog(*args)
    return result


if __name__ == "__main__":
    mcp.run()
