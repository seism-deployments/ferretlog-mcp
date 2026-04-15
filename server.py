#!/usr/bin/env python3
"""
ferretlog MCP Server — exposes ferretlog CLI functionality via FastMCP tools.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

mcp = FastMCP("ferretlog")


async def _run_ferretlog(*args: str, cwd: Optional[str] = None) -> str:
    """Run ferretlog CLI and return output."""
    cmd = [sys.executable, "-m", "ferretlog"] + list(args)
    # Try direct ferretlog command first, fallback to python -m
    env = os.environ.copy()

    try:
        proc = await asyncio.create_subprocess_exec(
            "ferretlog", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            return stdout.decode("utf-8", errors="replace")
        # If ferretlog binary failed, include stderr
        err = stderr.decode("utf-8", errors="replace")
        if err:
            return f"Error running ferretlog:\n{err}"
        return stdout.decode("utf-8", errors="replace")
    except FileNotFoundError:
        pass

    # Fallback: try running the ferretlog.py module directly
    ferretlog_py = Path(__file__).parent / "ferretlog.py"
    if ferretlog_py.exists():
        cmd = [sys.executable, str(ferretlog_py)] + list(args)
    else:
        # Last resort: python -c import ferretlog
        cmd = [sys.executable, "-c",
               f"import ferretlog; import sys; sys.argv = ['ferretlog'] + {list(args)!r}; ferretlog.main()"]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        if proc.returncode != 0 and err:
            return f"Error:\n{err}\n{output}"
        return output
    except Exception as e:
        return f"Failed to run ferretlog: {e}"


@mcp.tool()
async def list_runs(
    limit: int = 20,
    project_path: Optional[str] = None,
) -> dict:
    """
    List recent Claude Code agent runs in git-log style for the current project.
    Use this as the default starting point to see what agent sessions have been run,
    their tasks, costs, token usage, and duration.
    Shows run IDs needed for other commands.
    """
    args = []
    if limit and limit != 20:
        args += ["--limit", str(limit)]

    cwd = project_path if project_path else None

    output = await _run_ferretlog(*args, cwd=cwd)

    return {
        "output": output,
        "limit": limit,
        "project_path": project_path or os.getcwd(),
    }


@mcp.tool()
async def show_run(run_id: str) -> dict:
    """
    Display a full tool-by-tool breakdown of a specific agent run.
    Use this when you need to understand exactly what an agent did during a session
    — which files it read, what bash commands it ran, what edits it made,
    and full token/cost details.
    Requires a run ID from list_runs.
    """
    if not run_id or not run_id.strip():
        return {"error": "run_id is required. Obtain it from list_runs."}

    output = await _run_ferretlog("show", run_id.strip())

    return {
        "output": output,
        "run_id": run_id.strip(),
    }


@mcp.tool()
async def diff_runs(run_id_a: str, run_id_b: str) -> dict:
    """
    Compare two agent runs side-by-side to understand why the same or similar prompts
    produced different results. Use this to analyze differences in tool call sequences,
    files touched, duration, or cost between two sessions.
    """
    if not run_id_a or not run_id_a.strip():
        return {"error": "run_id_a is required. Obtain it from list_runs."}
    if not run_id_b or not run_id_b.strip():
        return {"error": "run_id_b is required. Obtain it from list_runs."}

    output = await _run_ferretlog("diff", run_id_a.strip(), run_id_b.strip())

    return {
        "output": output,
        "run_id_a": run_id_a.strip(),
        "run_id_b": run_id_b.strip(),
    }


@mcp.tool()
async def get_stats(project_path: Optional[str] = None) -> dict:
    """
    Show aggregate statistics across all agent runs for the current project,
    including total cost, total tokens consumed, total time spent,
    and per-model breakdowns.
    Use this to understand overall agent usage, spending, and efficiency trends.
    """
    cwd = project_path if project_path else None

    output = await _run_ferretlog("stats", cwd=cwd)

    return {
        "output": output,
        "project_path": project_path or os.getcwd(),
    }


if __name__ == "__main__":
    mcp.run()
