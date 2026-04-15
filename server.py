import uvicorn
from starlette.responses import JSONResponse
#!/usr/bin/env python3
"""ferretlog MCP server — git log for your Claude Code agent runs."""

from fastmcp import FastMCP
import os
import json
import subprocess
import tempfile
from typing import Optional
from pathlib import Path

mcp = FastMCP("ferretlog")


def _run_ferretlog(args: list[str], cwd: Optional[str] = None) -> dict:
    """Run the ferretlog CLI tool and capture output."""
    cmd = ["ferretlog"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd or os.getcwd(),
            timeout=30,
        )
        output = result.stdout
        error = result.stderr
        if result.returncode != 0 and not output:
            return {
                "success": False,
                "error": error or f"ferretlog exited with code {result.returncode}",
                "output": "",
            }
        return {
            "success": True,
            "output": output,
            "error": error if error else "",
            "returncode": result.returncode,
        }
    except FileNotFoundError:
        return {
            "success": False,
            "error": "ferretlog is not installed or not found in PATH. Install it with: pip install ferretlog",
            "output": "",
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "ferretlog command timed out after 30 seconds.",
            "output": "",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "output": "",
        }


@mcp.tool()
async def list_runs(
    limit: Optional[int] = 20,
    project_path: Optional[str] = None,
) -> dict:
    """List recent Claude Code agent runs in git log style for the current project.

    Use this to get an overview of all agent sessions, their tasks, costs, token
    usage, and duration. This is the default view and should be used when the user
    wants to see their agent history or recent activity.

    Args:
        limit: Maximum number of runs to display. Defaults to 20.
        project_path: Path to the project directory to list runs for.
                      Defaults to the current working directory.
    """
    args = []
    if limit and limit != 20:
        args.extend(["--limit", str(limit)])

    cwd = project_path if project_path else None
    result = _run_ferretlog(args, cwd=cwd)

    if not result["success"]:
        return {
            "error": result["error"],
            "suggestion": "Make sure ferretlog is installed: pip install ferretlog",
        }

    return {
        "runs_output": result["output"],
        "project_path": project_path or os.getcwd(),
        "limit": limit,
    }


@mcp.tool()
async def show_run(run_id: str) -> dict:
    """Show a full tool-by-tool breakdown of a specific agent run.

    Includes all tool calls made (read, edit, bash, etc.), files touched,
    token usage, cost, duration, and model used. Use this when the user wants
    to understand what happened in a specific session or replay/audit a run.

    Args:
        run_id: The short run ID (e.g. 'a3f2b1c9') or full session UUID to
                inspect. Obtainable from list_runs.
    """
    if not run_id or not run_id.strip():
        return {"error": "run_id is required and cannot be empty."}

    result = _run_ferretlog(["show", run_id.strip()])

    if not result["success"]:
        return {
            "error": result["error"],
            "run_id": run_id,
            "suggestion": "Use list_runs first to get valid run IDs.",
        }

    return {
        "run_id": run_id,
        "run_detail": result["output"],
    }


@mcp.tool()
async def diff_runs(run_id_a: str, run_id_b: str) -> dict:
    """Compare two agent runs side-by-side.

    Shows how they differed in approach, tool calls, files touched, tokens,
    and cost. Use this when the user wants to understand why the same prompt
    produced different results, or to compare two approaches to the same problem.

    Args:
        run_id_a: The short run ID or session UUID of the first run to compare.
        run_id_b: The short run ID or session UUID of the second run to compare.
    """
    if not run_id_a or not run_id_a.strip():
        return {"error": "run_id_a is required and cannot be empty."}
    if not run_id_b or not run_id_b.strip():
        return {"error": "run_id_b is required and cannot be empty."}

    if run_id_a.strip() == run_id_b.strip():
        return {"error": "run_id_a and run_id_b must be different run IDs."}

    result = _run_ferretlog(["diff", run_id_a.strip(), run_id_b.strip()])

    if not result["success"]:
        return {
            "error": result["error"],
            "run_id_a": run_id_a,
            "run_id_b": run_id_b,
            "suggestion": "Use list_runs first to get valid run IDs.",
        }

    return {
        "run_id_a": run_id_a,
        "run_id_b": run_id_b,
        "diff_output": result["output"],
    }


@mcp.tool()
async def get_stats(project_path: Optional[str] = None) -> dict:
    """Show aggregate statistics across all agent runs for the current project.

    Includes total cost, total tokens consumed, total time spent, number of
    sessions, average run duration, and per-model breakdowns. Use this when
    the user wants a high-level summary of their overall agent usage and spending.

    Args:
        project_path: Path to the project directory to aggregate stats for.
                      Defaults to the current working directory.
    """
    cwd = project_path if project_path else None
    result = _run_ferretlog(["stats"], cwd=cwd)

    if not result["success"]:
        return {
            "error": result["error"],
            "project_path": project_path or os.getcwd(),
            "suggestion": "Make sure ferretlog is installed: pip install ferretlog",
        }

    return {
        "project_path": project_path or os.getcwd(),
        "stats_output": result["output"],
    }




# ── Browser-friendly entrypoint ──────────────────────────────
class _BrowserFallback:
    """Intercept browser GETs to /mcp and return server info as JSON."""
    def __init__(self, app):
        self.app = app
    async def __call__(self, scope, receive, send):
        if (scope["type"] == "http"
            and scope["path"] == "/mcp"
            and scope["method"] == "GET"):
            headers = dict(scope.get("headers", []))
            accept = headers.get(b"accept", b"").decode()
            if "text/event-stream" not in accept:
                tools = []
                try:
                    for t in mcp._tool_manager._tools.values():
                        tools.append({"name": t.name, "description": t.description or ""})
                except Exception:
                    pass
                resp = JSONResponse({
                    "server": mcp.name,
                    "protocol": "MCP (Model Context Protocol)",
                    "transport": "streamable-http",
                    "endpoint": "/mcp",
                    "tools": tools,
                    "tool_count": len(tools),
                    "usage": "Connect with an MCP client (Claude Desktop, Cursor, etc.) using this URL."
                })
                await resp(scope, receive, send)
                return
        await self.app(scope, receive, send)

app = _BrowserFallback(mcp.http_app())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
