#!/usr/bin/env python3
"""
ferretlog MCP Server
Exposes ferretlog CLI functionality as MCP tools.
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


def _run_ferretlog(*args: str, cwd: Optional[str] = None) -> dict:
    """
    Run the ferretlog CLI with the given arguments.
    Returns a dict with stdout, stderr, and returncode.
    """
    cmd = [sys.executable, "-m", "ferretlog"] if False else ["ferretlog"]
    
    # Try ferretlog as a module first, fall back to direct script
    try:
        result = subprocess.run(
            ["ferretlog"] + list(args),
            capture_output=True,
            text=True,
            cwd=cwd or os.getcwd(),
            timeout=30,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "success": result.returncode == 0,
        }
    except FileNotFoundError:
        # Try python -m ferretlog
        try:
            result = subprocess.run(
                [sys.executable, "-m", "ferretlog"] + list(args),
                capture_output=True,
                text=True,
                cwd=cwd or os.getcwd(),
                timeout=30,
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "success": result.returncode == 0,
            }
        except FileNotFoundError:
            return {
                "stdout": "",
                "stderr": "ferretlog is not installed. Install it with: pip install ferretlog",
                "returncode": 1,
                "success": False,
            }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": "ferretlog command timed out after 30 seconds",
            "returncode": 1,
            "success": False,
        }


@mcp.tool()
def list_runs(
    limit: int = 20,
    project_path: Optional[str] = None,
) -> dict:
    """
    List recent Claude Code agent runs in git-log style.
    
    Use this to get an overview of recent agent sessions, their tasks, costs,
    token usage, and duration. Shows all runs for the current project by default.
    Use this as the starting point when a user wants to see their agent history.
    """
    args = []
    
    if limit and limit != 20:
        args.extend(["--limit", str(limit)])
    
    cwd = project_path if project_path else None
    
    result = _run_ferretlog(*args, cwd=cwd)
    
    if not result["success"]:
        return {
            "error": result["stderr"] or "Failed to list runs",
            "output": result["stdout"],
        }
    
    return {
        "output": result["stdout"],
        "project_path": project_path or os.getcwd(),
        "limit": limit,
    }


@mcp.tool()
def show_run(run_id: str) -> dict:
    """
    Show a full tool-by-tool breakdown of a specific agent run.
    
    Use this when a user wants to understand exactly what an agent did during
    a session — every file read, bash command, and edit made. Requires a run ID
    (short hash) from list_runs.
    """
    if not run_id:
        return {"error": "run_id is required"}
    
    result = _run_ferretlog("show", run_id)
    
    if not result["success"]:
        return {
            "error": result["stderr"] or f"Failed to show run {run_id}",
            "output": result["stdout"],
            "run_id": run_id,
        }
    
    return {
        "output": result["stdout"],
        "run_id": run_id,
    }


@mcp.tool()
def diff_runs(run_id_a: str, run_id_b: str) -> dict:
    """
    Compare two agent runs side-by-side to see how they differed in approach,
    tool calls, files touched, cost, and duration.
    
    Use this when a user wants to understand why the same or similar prompts led
    to different outcomes, or to compare efficiency between runs.
    """
    if not run_id_a:
        return {"error": "run_id_a is required"}
    if not run_id_b:
        return {"error": "run_id_b is required"}
    
    result = _run_ferretlog("diff", run_id_a, run_id_b)
    
    if not result["success"]:
        return {
            "error": result["stderr"] or f"Failed to diff runs {run_id_a} and {run_id_b}",
            "output": result["stdout"],
            "run_id_a": run_id_a,
            "run_id_b": run_id_b,
        }
    
    return {
        "output": result["stdout"],
        "run_id_a": run_id_a,
        "run_id_b": run_id_b,
    }


@mcp.tool()
def get_stats(project_path: Optional[str] = None) -> dict:
    """
    Show aggregate statistics across all agent runs for a project.
    
    Includes total cost, total tokens used, total time spent, average run
    duration, and number of sessions. Use this when a user wants a high-level
    summary of their overall agent usage or to understand cumulative costs.
    """
    cwd = project_path if project_path else None
    
    result = _run_ferretlog("stats", cwd=cwd)
    
    if not result["success"]:
        return {
            "error": result["stderr"] or "Failed to get stats",
            "output": result["stdout"],
        }
    
    return {
        "output": result["stdout"],
        "project_path": project_path or os.getcwd(),
    }


if __name__ == "__main__":
    mcp.run()
