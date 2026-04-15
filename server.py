import uvicorn
from starlette.responses import JSONResponse
#!/usr/bin/env python3
"""
FastMCP server for ferretlog 🐾 — git log for your Claude Code agent runs.
"""

from fastmcp import FastMCP
import subprocess
import os
import sys
from typing import Optional

mcp = FastMCP("ferretlog")


def _run_ferretlog(*args: str, cwd: Optional[str] = None) -> dict:
    """Run the ferretlog CLI command and return structured output."""
    cmd = [sys.executable, "-m", "ferretlog"] if False else ["ferretlog"]
    
    # Try ferretlog as installed CLI first, fallback to python -c approach
    full_cmd = ["ferretlog"] + list(args)
    
    run_kwargs = {
        "capture_output": True,
        "text": True,
        "env": os.environ.copy(),
    }
    
    if cwd:
        run_kwargs["cwd"] = cwd
    
    try:
        result = subprocess.run(full_cmd, **run_kwargs)
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.stderr else None,
            "returncode": result.returncode,
        }
    except FileNotFoundError:
        # ferretlog not found as a command, try via python -m
        full_cmd_py = [sys.executable, "-c",
                       "import ferretlog; import sys; sys.argv = ['ferretlog'] + sys.argv[1:]; ferretlog.main()"
                       ] + list(args)
        try:
            result = subprocess.run(full_cmd_py, **run_kwargs)
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.stderr else None,
                "returncode": result.returncode,
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "returncode": -1,
            }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "returncode": -1,
        }


@mcp.tool()
async def list_runs(
    limit: int = 20,
    project_path: Optional[str] = None,
) -> dict:
    """List recent Claude Code agent runs in git log style for the current project.
    
    Use this as the default starting point to get an overview of agent history,
    see run IDs, tasks, durations, token usage, and costs. Call this when the
    user wants to see their agent run history or find a specific run.
    """
    args = []
    if limit and limit != 20:
        args.extend(["--limit", str(limit)])
    
    result = _run_ferretlog(*args, cwd=project_path)
    
    return {
        "tool": "list_runs",
        "limit": limit,
        "project_path": project_path or os.getcwd(),
        "success": result["success"],
        "output": result["output"],
        "error": result["error"],
    }


@mcp.tool()
async def show_run(run_id: str) -> dict:
    """Show a full tool-by-tool breakdown of a specific agent run.
    
    Includes all tool calls (read, edit, bash, etc.), files touched,
    token usage, cost, model, and duration. Use this when the user wants
    to understand what happened in a specific run or replay its steps.
    """
    if not run_id:
        return {
            "success": False,
            "error": "run_id is required",
            "output": "",
        }
    
    result = _run_ferretlog("show", run_id)
    
    return {
        "tool": "show_run",
        "run_id": run_id,
        "success": result["success"],
        "output": result["output"],
        "error": result["error"],
    }


@mcp.tool()
async def diff_runs(run_id_a: str, run_id_b: str) -> dict:
    """Compare two agent runs side-by-side.
    
    Shows how they differed in approach, tool calls, files touched, tokens,
    cost, and duration. Use this when the user wants to understand why the
    same or similar prompt produced different results, or to compare agent
    behavior across runs.
    """
    if not run_id_a or not run_id_b:
        return {
            "success": False,
            "error": "Both run_id_a and run_id_b are required",
            "output": "",
        }
    
    result = _run_ferretlog("diff", run_id_a, run_id_b)
    
    return {
        "tool": "diff_runs",
        "run_id_a": run_id_a,
        "run_id_b": run_id_b,
        "success": result["success"],
        "output": result["output"],
        "error": result["error"],
    }


@mcp.tool()
async def get_stats(project_path: Optional[str] = None) -> dict:
    """Show aggregate statistics across all agent runs for the current project.
    
    Includes total cost, total tokens, total time spent, number of runs,
    average cost per run, and most-used models. Use this when the user wants
    a high-level summary of their overall Claude Code usage or spending.
    """
    result = _run_ferretlog("stats", cwd=project_path)
    
    return {
        "tool": "get_stats",
        "project_path": project_path or os.getcwd(),
        "success": result["success"],
        "output": result["output"],
        "error": result["error"],
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
