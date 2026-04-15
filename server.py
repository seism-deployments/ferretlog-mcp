#!/usr/bin/env python3
"""ferretlog MCP server — git log for your Claude Code agent runs."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

mcp = FastMCP("ferretlog")


def _run_ferretlog(*args: str, cwd: Optional[str] = None) -> str:
    """Run the ferretlog CLI and return its output."""
    cmd = [sys.executable, "-m", "ferretlog"] if False else ["ferretlog"]
    # Try ferretlog directly; fall back to python -c import
    full_cmd = ["ferretlog"] + list(args)
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            cwd=cwd or os.getcwd(),
            timeout=30,
        )
        output = result.stdout
        if result.returncode != 0 and result.stderr:
            output = output + "\nSTDERR: " + result.stderr
        return output.strip() if output.strip() else result.stderr.strip()
    except FileNotFoundError:
        # ferretlog not on PATH, try python -m ferretlog
        full_cmd2 = [sys.executable, "-c", f"import ferretlog; import sys; sys.argv = ['ferretlog'] + {list(args)!r}; ferretlog.main()"]
        try:
            result2 = subprocess.run(
                full_cmd2,
                capture_output=True,
                text=True,
                cwd=cwd or os.getcwd(),
                timeout=30,
            )
            output = result2.stdout
            if result2.returncode != 0 and result2.stderr:
                output = output + "\nSTDERR: " + result2.stderr
            return output.strip() if output.strip() else result2.stderr.strip()
        except Exception as e:
            return f"Error running ferretlog: {e}"
    except subprocess.TimeoutExpired:
        return "Error: ferretlog command timed out after 30 seconds."
    except Exception as e:
        return f"Error running ferretlog: {e}"


@mcp.tool()
def list_runs(
    limit: int = 20,
    project_path: Optional[str] = None,
) -> dict:
    """List recent Claude Code agent runs in git log style for the current project.

    Use this to get an overview of past agent sessions, their tasks, costs,
    token usage, and duration. Shows run IDs needed for other commands.

    Args:
        limit: Maximum number of recent runs to display (default 20).
        project_path: Path to the project directory. Defaults to current working directory.

    Returns:
        A dict with 'output' containing the formatted run list.
    """
    args = ["--limit", str(limit)] if limit != 20 else []
    cwd = project_path or os.getcwd()
    output = _run_ferretlog(*args, cwd=cwd)
    return {"output": output, "project_path": cwd, "limit": limit}


@mcp.tool()
def show_run(run_id: str) -> dict:
    """Show a full tool-by-tool breakdown of a specific agent run.

    Includes every tool call made, files touched, token usage, cost, and timing.
    Use this when you need to understand exactly what the agent did during a
    specific session.

    Args:
        run_id: The run ID (short hash) to inspect, e.g. 'a3f2b1c9'.
                Obtain run IDs from list_runs.

    Returns:
        A dict with 'output' containing the detailed run breakdown.
    """
    if not run_id or not run_id.strip():
        return {"error": "run_id is required and cannot be empty."}
    output = _run_ferretlog("show", run_id.strip())
    return {"output": output, "run_id": run_id.strip()}


@mcp.tool()
def diff_runs(run_id_a: str, run_id_b: str) -> dict:
    """Compare two agent runs side by side.

    Shows how they differed in tool calls, files touched, duration, and cost.
    Use this when the same task was attempted multiple times and you want to
    understand why the outcomes differed.

    Args:
        run_id_a: The first run ID to compare, e.g. 'a3f2b1c9'.
                  Obtain from list_runs.
        run_id_b: The second run ID to compare, e.g. '9c1b2d3e'.
                  Obtain from list_runs.

    Returns:
        A dict with 'output' containing the side-by-side comparison.
    """
    if not run_id_a or not run_id_a.strip():
        return {"error": "run_id_a is required and cannot be empty."}
    if not run_id_b or not run_id_b.strip():
        return {"error": "run_id_b is required and cannot be empty."}
    output = _run_ferretlog("diff", run_id_a.strip(), run_id_b.strip())
    return {
        "output": output,
        "run_id_a": run_id_a.strip(),
        "run_id_b": run_id_b.strip(),
    }


@mcp.tool()
def get_stats(project_path: Optional[str] = None) -> dict:
    """Show aggregate statistics across all agent runs for the current project.

    Includes total cost, total tokens consumed, total time spent, number of
    sessions, and averages per run. Use this to understand overall AI usage
    and costs.

    Args:
        project_path: Path to the project directory. Defaults to current working directory.

    Returns:
        A dict with 'output' containing the aggregate statistics.
    """
    cwd = project_path or os.getcwd()
    output = _run_ferretlog("stats", cwd=cwd)
    return {"output": output, "project_path": cwd}


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))))
