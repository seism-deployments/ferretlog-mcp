#!/usr/bin/env python3
"""ferretlog MCP server — git log for your Claude Code agent runs."""

import subprocess
import sys
from typing import Optional
from fastmcp import FastMCP

mcp = FastMCP("ferretlog")


def _run_ferretlog(*args: str) -> str:
    """Run the ferretlog CLI with given arguments and return output."""
    cmd = [sys.executable, "-m", "ferretlog"] + list(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout
        if result.returncode != 0 and result.stderr:
            output += "\n" + result.stderr
        return output.strip() if output.strip() else "No output returned."
    except FileNotFoundError:
        # Try direct ferretlog command
        try:
            cmd2 = ["ferretlog"] + list(args)
            result2 = subprocess.run(
                cmd2,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output2 = result2.stdout
            if result2.returncode != 0 and result2.stderr:
                output2 += "\n" + result2.stderr
            return output2.strip() if output2.strip() else "No output returned."
        except FileNotFoundError:
            return "Error: ferretlog is not installed. Please run: pip install ferretlog"
    except subprocess.TimeoutExpired:
        return "Error: ferretlog command timed out after 30 seconds."
    except Exception as e:
        return f"Error running ferretlog: {str(e)}"


@mcp.tool()
async def list_runs(
    limit: Optional[int] = 20,
    no_color: Optional[bool] = False,
) -> str:
    """List recent Claude Code agent runs in git log style for the current project.

    Use this as the default overview when a user wants to see their agent history,
    recent sessions, or what their AI assistant has been doing. Shows run IDs,
    dates, tasks, tool call counts, files touched, duration, model, tokens, and cost.
    """
    args = []
    if limit is not None and limit != 20:
        args.extend(["--limit", str(limit)])
    if no_color:
        args.append("--no-color")
    return _run_ferretlog(*args)


@mcp.tool()
async def show_run(run_id: str) -> str:
    """Display a full tool-by-tool breakdown of a specific Claude Code agent run.

    Use this when a user wants to understand exactly what happened in a particular
    session — what files were read, what edits were made, what commands were run,
    tokens used, and cost. Requires a run ID (short hash) from list_runs.
    """
    if not run_id or not run_id.strip():
        return "Error: run_id is required. Get a run ID from list_runs first."
    return _run_ferretlog("show", run_id.strip())


@mcp.tool()
async def diff_runs(run_id_a: str, run_id_b: str) -> str:
    """Compare two Claude Code agent runs side-by-side.

    Use this when a user wants to investigate differences between two sessions —
    different tool sequences, file changes, token usage, or approaches taken.
    Helps understand why the same or similar prompt produced different behavior.
    """
    if not run_id_a or not run_id_a.strip():
        return "Error: run_id_a is required."
    if not run_id_b or not run_id_b.strip():
        return "Error: run_id_b is required."
    return _run_ferretlog("diff", run_id_a.strip(), run_id_b.strip())


@mcp.tool()
async def get_stats(no_color: Optional[bool] = False) -> str:
    """Show aggregate statistics across all Claude Code agent runs for the current project.

    Use this when a user wants a summary of total cost, total tokens consumed,
    total time spent, number of sessions, average session length, or overall usage
    patterns. Good for cost tracking and productivity analysis.
    """
    args = ["stats"]
    if no_color:
        args.append("--no-color")
    return _run_ferretlog(*args)


if __name__ == "__main__":
    mcp.run()
