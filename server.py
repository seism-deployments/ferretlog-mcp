#!/usr/bin/env python3
"""
fastMCP server for ferretlog - git log for your Claude Code agent runs.
"""

import json
import os
import subprocess
import sys
from typing import Optional

from fastmcp import FastMCP

mcp = FastMCP("ferretlog")


def _run_ferretlog(*args) -> str:
    """Run ferretlog CLI with given arguments and return output."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ferretlog"] + list(args),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout
        # Try running as direct script if module invocation fails
        result2 = subprocess.run(
            ["ferretlog"] + list(args),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result2.returncode == 0:
            return result2.stdout
        # Return stderr as fallback info
        combined = result2.stdout + result2.stderr
        return combined if combined.strip() else result.stdout + result.stderr
    except FileNotFoundError:
        return "Error: ferretlog is not installed. Install it with: pip install ferretlog"
    except subprocess.TimeoutExpired:
        return "Error: ferretlog command timed out after 30 seconds."
    except Exception as e:
        return f"Error running ferretlog: {str(e)}"


def _run_ferretlog_in_dir(cwd: Optional[str], *args) -> str:
    """Run ferretlog CLI in a specific directory."""
    try:
        env = os.environ.copy()
        run_cwd = cwd if cwd else os.getcwd()

        result = subprocess.run(
            [sys.executable, "-m", "ferretlog"] + list(args),
            capture_output=True,
            text=True,
            timeout=30,
            cwd=run_cwd,
            env=env,
        )
        if result.returncode == 0:
            return result.stdout

        result2 = subprocess.run(
            ["ferretlog"] + list(args),
            capture_output=True,
            text=True,
            timeout=30,
            cwd=run_cwd,
            env=env,
        )
        output = result2.stdout
        if result2.returncode != 0:
            output = output + result2.stderr if output else result2.stderr
        if not output.strip():
            output = result.stdout + result.stderr
        return output if output.strip() else "No output returned from ferretlog."
    except FileNotFoundError:
        return "Error: ferretlog is not installed. Install it with: pip install ferretlog"
    except subprocess.TimeoutExpired:
        return "Error: ferretlog command timed out after 30 seconds."
    except Exception as e:
        return f"Error running ferretlog: {str(e)}"


@mcp.tool()
async def list_runs(
    limit: int = 20,
    project_path: Optional[str] = None,
) -> dict:
    """
    List recent Claude Code agent runs in git log style.

    Use this as the default starting point to see what the agent has been doing,
    browse history, or find a specific run ID for further inspection. Shows
    commit-like IDs, task descriptions, timestamps, tool call counts, files
    changed, duration, model, tokens, and cost.

    Args:
        limit: Maximum number of recent runs to display. Increase to see more history.
        project_path: Path to the project directory to list runs for. Defaults to current working directory.

    Returns:
        A dict with 'output' containing the formatted list of runs.
    """
    args = []
    if limit and limit != 20:
        args += ["--limit", str(limit)]

    output = _run_ferretlog_in_dir(project_path, *args)

    return {
        "output": output,
        "limit": limit,
        "project_path": project_path or os.getcwd(),
    }


@mcp.tool()
async def show_run(run_id: str) -> dict:
    """
    Show a full tool-by-tool breakdown of a specific agent run.

    Use this when you need to understand exactly what the agent did step-by-step:
    which files it read, what bash commands it ran, what edits it made, along
    with token usage, cost, duration, and files touched. Requires a run ID
    from list_runs.

    Args:
        run_id: The short run ID (e.g. 'a3f2b1c9') from ferretlog list output to inspect in detail.

    Returns:
        A dict with 'output' containing the detailed run breakdown.
    """
    if not run_id or not run_id.strip():
        return {"error": "run_id is required. Get one from list_runs first.", "output": ""}

    output = _run_ferretlog("show", run_id.strip())

    return {
        "output": output,
        "run_id": run_id.strip(),
    }


@mcp.tool()
async def diff_runs(run_id_a: str, run_id_b: str) -> dict:
    """
    Compare two agent runs side-by-side to understand why the same or similar
    task went differently.

    Use this when debugging inconsistent agent behavior, comparing approaches
    across runs, or understanding why one run was more expensive or took longer
    than another.

    Args:
        run_id_a: The first run ID to compare (e.g. 'a3f2b1c9').
        run_id_b: The second run ID to compare against the first (e.g. '9c1b2d3e').

    Returns:
        A dict with 'output' containing the side-by-side diff of the two runs.
    """
    if not run_id_a or not run_id_a.strip():
        return {"error": "run_id_a is required.", "output": ""}
    if not run_id_b or not run_id_b.strip():
        return {"error": "run_id_b is required.", "output": ""}

    output = _run_ferretlog("diff", run_id_a.strip(), run_id_b.strip())

    return {
        "output": output,
        "run_id_a": run_id_a.strip(),
        "run_id_b": run_id_b.strip(),
    }


@mcp.tool()
async def get_stats(project_path: Optional[str] = None) -> dict:
    """
    Show aggregate statistics across all agent runs: total cost, total tokens
    consumed, total time spent, average run duration, most-used models, and
    other summary metrics.

    Use this to understand overall AI usage, estimate spend, or audit how the
    agent has been used across a project's entire history.

    Args:
        project_path: Path to the project directory to compute stats for. Defaults to current working directory.

    Returns:
        A dict with 'output' containing aggregate statistics.
    """
    output = _run_ferretlog_in_dir(project_path, "stats")

    return {
        "output": output,
        "project_path": project_path or os.getcwd(),
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))))
