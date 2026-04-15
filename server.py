from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
import uvicorn
#!/usr/bin/env python3
"""
FastMCP server for ferretlog - git log for Claude Code agent runs.
"""

from fastmcp import FastMCP
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

mcp = FastMCP("ferretlog")


def _run_ferretlog(args: list[str], cwd: Optional[str] = None) -> dict:
    """Run ferretlog CLI and return structured output."""
    cmd = [sys.executable, "-m", "ferretlog"] + args
    # Try ferretlog directly if available
    try:
        result = subprocess.run(
            ["ferretlog"] + args,
            capture_output=True,
            text=True,
            cwd=cwd or os.getcwd(),
            timeout=30
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except FileNotFoundError:
        # ferretlog not in PATH, try via python -c import
        result = subprocess.run(
            [sys.executable, "-c",
             "import ferretlog, sys; sys.argv = ['ferretlog'] + " + repr(args) + "; ferretlog.main()"],
            capture_output=True,
            text=True,
            cwd=cwd or os.getcwd(),
            timeout=30
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }


def _parse_runs_from_output(output: str) -> list[dict]:
    """Parse ferretlog list output into structured run records."""
    runs = []
    lines = output.split("\n")
    current_run = None

    for line in lines:
        # Strip ANSI escape codes for parsing
        import re
        clean = re.sub(r'\033\[[0-9;]*m', '', line).strip()
        if not clean:
            continue

        # Try to detect a run line: starts with short hex id (8 chars)
        # Pattern: <id>  <date>  <task>  [branch]
        run_match = re.match(
            r'^([0-9a-f]{8})\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s+(.+?)(?:\s+\[(\S+)\])?$',
            clean
        )
        if run_match:
            if current_run:
                runs.append(current_run)
            current_run = {
                "id": run_match.group(1),
                "date": run_match.group(2),
                "task": run_match.group(3).strip(),
                "branch": run_match.group(4),
            }
            continue

        # Stats line: N calls  N files  Xs  model  N tok  ~$N
        stats_match = re.match(
            r'^(\d+)\s+calls?\s+(\d+)\s+files?\s+([\dms]+)\s+(\S+)\s+([\d,]+)\s+tok\s+~(\$[\d.]+)',
            clean
        )
        if stats_match and current_run:
            current_run["tool_calls"] = int(stats_match.group(1))
            current_run["files_touched"] = int(stats_match.group(2))
            current_run["duration"] = stats_match.group(3)
            current_run["model"] = stats_match.group(4)
            current_run["tokens"] = stats_match.group(5).replace(",", "")
            current_run["cost"] = stats_match.group(6)

    if current_run:
        runs.append(current_run)

    return runs


@mcp.tool()
async def list_runs(
    limit: int = 20,
    project_path: Optional[str] = None
) -> dict:
    """List recent Claude Code agent runs in git log style for the current project.
    Use this as the default starting point to see what AI agent sessions have been run,
    with summaries including task description, tool calls, files touched, duration, model,
    tokens, and cost."""
    args = []
    if limit and limit != 20:
        args += ["--limit", str(limit)]

    cwd = project_path or os.getcwd()

    result = _run_ferretlog(args, cwd=cwd)

    if result["returncode"] != 0 and result["stderr"]:
        return {
            "error": result["stderr"],
            "raw_output": result["stdout"]
        }

    raw_output = result["stdout"]
    parsed_runs = _parse_runs_from_output(raw_output)

    return {
        "project_path": cwd,
        "limit": limit,
        "runs": parsed_runs,
        "raw_output": raw_output,
        "count": len(parsed_runs)
    }


@mcp.tool()
async def show_run(run_id: str) -> dict:
    """Show a full tool-by-tool breakdown of a specific agent run, including every tool
    call made (read, edit, bash, etc.), files touched, token usage, cost, duration, and
    model. Use this when the user wants to understand exactly what happened in a particular
    session."""
    result = _run_ferretlog(["show", run_id])

    if result["returncode"] != 0 and result["stderr"]:
        return {
            "error": result["stderr"],
            "run_id": run_id,
            "raw_output": result["stdout"]
        }

    raw_output = result["stdout"]

    # Parse structured info from show output
    import re
    clean_output = re.sub(r'\033\[[0-9;]*m', '', raw_output)

    parsed = {"run_id": run_id, "raw_output": raw_output}

    for line in clean_output.split("\n"):
        line = line.strip()
        if line.startswith("run"):
            m = re.match(r'^run\s+([0-9a-f]+)', line)
            if m:
                parsed["run_id"] = m.group(1)
        elif line.startswith("task"):
            m = re.match(r'^task\s+(.+)', line)
            if m:
                parsed["task"] = m.group(1).strip()
        elif line.startswith("date"):
            m = re.match(r'^date\s+(.+)', line)
            if m:
                parsed["date"] = m.group(1).strip()
        elif line.startswith("duration"):
            m = re.match(r'^duration\s+(.+)', line)
            if m:
                parsed["duration"] = m.group(1).strip()
        elif line.startswith("model"):
            m = re.match(r'^model\s+(.+)', line)
            if m:
                parsed["model"] = m.group(1).strip()
        elif line.startswith("branch"):
            m = re.match(r'^branch\s+(.+)', line)
            if m:
                parsed["branch"] = m.group(1).strip()
        elif line.startswith("tokens"):
            m = re.match(r'^tokens\s+(.+)', line)
            if m:
                parsed["tokens"] = m.group(1).strip()

    # Parse tool calls
    tool_calls = []
    in_tools_section = False
    for line in clean_output.split("\n"):
        stripped = line.strip()
        if "tool calls:" in stripped.lower():
            in_tools_section = True
            continue
        if "files touched:" in stripped.lower():
            in_tools_section = False
            continue
        if in_tools_section and stripped:
            m = re.match(r'^(\d+)\s+(\w+)\s+(.*)', stripped)
            if m:
                tool_calls.append({
                    "index": int(m.group(1)),
                    "tool": m.group(2),
                    "detail": m.group(3).strip()
                })

    if tool_calls:
        parsed["tool_calls"] = tool_calls

    # Parse files touched
    files_touched = []
    in_files_section = False
    for line in clean_output.split("\n"):
        stripped = line.strip()
        if "files touched:" in stripped.lower():
            in_files_section = True
            continue
        if "tool calls:" in stripped.lower():
            in_files_section = False
            continue
        if in_files_section and stripped:
            m = re.match(r'^([MAD])\s+(.+)', stripped)
            if m:
                files_touched.append({
                    "status": m.group(1),
                    "path": m.group(2).strip()
                })
            elif not re.match(r'^[─=]', stripped):
                files_touched.append({"path": stripped})

    if files_touched:
        parsed["files_touched"] = files_touched

    return parsed


@mcp.tool()
async def diff_runs(run_id_a: str, run_id_b: str) -> dict:
    """Compare two agent runs side-by-side to see how they differed — tool calls, files
    touched, tokens, cost, and duration. Use this when the user wants to understand why
    the same or similar prompt led to different outcomes, or to compare efficiency between
    runs."""
    result = _run_ferretlog(["diff", run_id_a, run_id_b])

    if result["returncode"] != 0 and result["stderr"]:
        return {
            "error": result["stderr"],
            "run_id_a": run_id_a,
            "run_id_b": run_id_b,
            "raw_output": result["stdout"]
        }

    raw_output = result["stdout"]

    return {
        "run_id_a": run_id_a,
        "run_id_b": run_id_b,
        "raw_output": raw_output,
        "comparison_note": (
            "Lines prefixed with '=' are identical in both runs. "
            "Lines with '-' exist only in run A. "
            "Lines with '+' exist only in run B. "
            "Lines with '~' differ between runs."
        )
    }


@mcp.tool()
async def get_stats(project_path: Optional[str] = None) -> dict:
    """Show aggregate statistics across all agent runs for the current project: total cost,
    total tokens, total time spent, number of sessions, average cost per run, most-used
    models, and most-touched files. Use this when the user wants a high-level overview of
    their AI usage and spend."""
    cwd = project_path or os.getcwd()

    result = _run_ferretlog(["stats"], cwd=cwd)

    if result["returncode"] != 0 and result["stderr"]:
        return {
            "error": result["stderr"],
            "project_path": cwd,
            "raw_output": result["stdout"]
        }

    raw_output = result["stdout"]

    # Parse structured stats from output
    import re
    clean_output = re.sub(r'\033\[[0-9;]*m', '', raw_output)

    parsed = {"project_path": cwd, "raw_output": raw_output}

    for line in clean_output.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        # sessions / runs count
        m = re.search(r'(\d+)\s+(?:sessions?|runs?)', stripped, re.I)
        if m:
            parsed["total_runs"] = int(m.group(1))

        # total cost
        m = re.search(r'total\s+cost[:\s]+~?(\$[\d.]+)', stripped, re.I)
        if m:
            parsed["total_cost"] = m.group(1)

        # total tokens
        m = re.search(r'total\s+tokens?[:\s]+([\d,]+)', stripped, re.I)
        if m:
            parsed["total_tokens"] = m.group(1).replace(",", "")

        # total time
        m = re.search(r'total\s+time[:\s]+([\dhmins ]+)', stripped, re.I)
        if m:
            parsed["total_time"] = m.group(1).strip()

        # average cost per run
        m = re.search(r'avg(?:erage)?\s+cost[:\s]+~?(\$[\d.]+)', stripped, re.I)
        if m:
            parsed["avg_cost_per_run"] = m.group(1)

    return parsed




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
