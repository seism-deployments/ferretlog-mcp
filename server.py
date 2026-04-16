from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
import uvicorn
#!/usr/bin/env python3
"""FastMCP server for ferretlog - git log for Claude Code agent runs."""

from fastmcp import FastMCP
import os
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

mcp = FastMCP("ferretlog")


def _run_ferretlog(args: list[str], cwd: Optional[str] = None) -> dict:
    """Run the ferretlog CLI tool and return output."""
    try:
        cmd = [sys.executable, "-m", "ferretlog"] + args
        # Try direct ferretlog command first
        result = subprocess.run(
            ["ferretlog"] + args,
            capture_output=True,
            text=True,
            cwd=cwd or os.getcwd(),
            timeout=30
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None
        }
    except FileNotFoundError:
        # Try python -c import approach
        try:
            result = subprocess.run(
                [sys.executable, "-c", f"import ferretlog; import sys; sys.argv = ['ferretlog'] + {json.dumps(args)}; ferretlog.main()"],
                capture_output=True,
                text=True,
                cwd=cwd or os.getcwd(),
                timeout=30
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e)
            }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "",
            "error": "Command timed out after 30 seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e)
        }


def _run_ferretlog_direct(args: list[str]) -> dict:
    """Run ferretlog by directly invoking it via Python."""
    # Build the command - try multiple approaches
    commands_to_try = [
        ["ferretlog"] + args,
        [sys.executable, "-m", "ferretlog"] + args,
    ]

    last_error = None
    for cmd in commands_to_try:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=os.getcwd(),
                timeout=30
            )
            if result.returncode == 0 or result.stdout:
                return {
                    "success": result.returncode == 0,
                    "output": result.stdout,
                    "error": result.stderr if result.returncode != 0 else None,
                    "raw": result.stdout
                }
            last_error = result.stderr
        except FileNotFoundError as e:
            last_error = str(e)
            continue
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "",
                "error": "Command timed out after 30 seconds"
            }
        except Exception as e:
            last_error = str(e)
            continue

    # If all commands failed, try reading Claude logs directly
    return _read_claude_logs_directly(args)


def _read_claude_logs_directly(args: list[str]) -> dict:
    """Fallback: Read Claude Code logs directly from ~/.claude/projects/."""
    CLAUDE_DIR = Path.home() / ".claude" / "projects"

    if not CLAUDE_DIR.exists():
        return {
            "success": False,
            "output": "",
            "error": f"Claude Code logs directory not found at {CLAUDE_DIR}. Please ensure Claude Code has been used and ferretlog is installed ('pip install ferretlog')."
        }

    # Collect all sessions
    sessions = []
    for project_dir in CLAUDE_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl_file in project_dir.glob("*.jsonl"):
            try:
                session = _parse_session(jsonl_file)
                if session:
                    sessions.append(session)
            except Exception:
                continue

    sessions.sort(key=lambda s: s.get("start_time", ""), reverse=True)

    if not args or args[0] not in ["show", "diff", "stats"]:
        # list command
        limit = 20
        all_projects = False
        for i, arg in enumerate(args):
            if arg == "--limit" and i + 1 < len(args):
                try:
                    limit = int(args[i + 1])
                except Exception:
                    pass
            if arg == "--all":
                all_projects = True

        if not all_projects:
            cwd = str(Path.cwd())
            sessions = [s for s in sessions if s.get("cwd", "") == cwd or True]  # include all for now

        sessions = sessions[:limit]
        output = _format_list(sessions)
        return {"success": True, "output": output, "error": None, "sessions": sessions}

    elif args[0] == "show" and len(args) > 1:
        run_id = args[1]
        session = _find_session_by_id(sessions, run_id)
        if not session:
            return {"success": False, "output": "", "error": f"Run '{run_id}' not found"}
        output = _format_show(session)
        return {"success": True, "output": output, "error": None, "session": session}

    elif args[0] == "diff" and len(args) > 2:
        run_id_a = args[1]
        run_id_b = args[2]
        session_a = _find_session_by_id(sessions, run_id_a)
        session_b = _find_session_by_id(sessions, run_id_b)
        if not session_a:
            return {"success": False, "output": "", "error": f"Run '{run_id_a}' not found"}
        if not session_b:
            return {"success": False, "output": "", "error": f"Run '{run_id_b}' not found"}
        output = _format_diff(session_a, session_b)
        return {"success": True, "output": output, "error": None}

    elif args[0] == "stats":
        all_projects = "--all" in args
        if not all_projects:
            cwd = str(Path.cwd())
            filtered = [s for s in sessions if s.get("cwd", "") == cwd]
            if not filtered:
                filtered = sessions
        else:
            filtered = sessions
        output = _format_stats(filtered)
        return {"success": True, "output": output, "error": None}

    return {"success": False, "output": "", "error": "Unknown command"}


def _parse_session(jsonl_file: Path) -> Optional[dict]:
    """Parse a Claude Code JSONL session file."""
    messages = []
    cwd = None
    start_time = None
    end_time = None

    try:
        with open(jsonl_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    messages.append(obj)
                    if cwd is None and obj.get("cwd"):
                        cwd = obj["cwd"]
                    ts = obj.get("timestamp") or obj.get("ts")
                    if ts:
                        if start_time is None:
                            start_time = ts
                        end_time = ts
                except Exception:
                    continue
    except Exception:
        return None

    if not messages:
        return None

    session_uuid = jsonl_file.stem
    short_id = session_uuid[:8] if len(session_uuid) >= 8 else session_uuid

    # Extract tool calls
    tool_calls = []
    files_touched = set()
    models_used = set()
    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_tokens = 0
    first_user_text = None

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("message", {}).get("content", []) if "message" in msg else msg.get("content", [])
        model = msg.get("message", {}).get("model") or msg.get("model")
        if model:
            models_used.add(model)

        usage = msg.get("message", {}).get("usage") or msg.get("usage", {})
        if usage:
            total_input_tokens += usage.get("input_tokens", 0)
            total_output_tokens += usage.get("output_tokens", 0)
            total_cache_tokens += usage.get("cache_read_input_tokens", 0)

        if isinstance(content, str):
            if role == "user" and first_user_text is None:
                first_user_text = content[:80]
            continue

        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "")
                if btype == "text" and role == "user" and first_user_text is None:
                    txt = block.get("text", "")
                    if txt.strip():
                        first_user_text = txt.strip()[:80]
                elif btype == "tool_use":
                    tool_name = block.get("name", "unknown")
                    tool_input = block.get("input", {})
                    call_info = {"tool": tool_name, "input": tool_input}

                    # Extract file paths
                    file_path = tool_input.get("path") or tool_input.get("file_path") or tool_input.get("filename")
                    if file_path:
                        files_touched.add(file_path)
                        call_info["file"] = file_path

                    # Extract bash command
                    cmd = tool_input.get("command") or tool_input.get("cmd")
                    if cmd:
                        call_info["command"] = cmd[:100]

                    tool_calls.append(call_info)

    # Calculate duration
    duration_secs = None
    if start_time and end_time:
        try:
            from datetime import datetime
            def parse_ts(ts):
                if isinstance(ts, (int, float)):
                    return datetime.fromtimestamp(ts)
                for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"]:
                    try:
                        return datetime.strptime(ts, fmt)
                    except Exception:
                        continue
                return None
            t1 = parse_ts(start_time)
            t2 = parse_ts(end_time)
            if t1 and t2:
                duration_secs = abs((t2 - t1).total_seconds())
        except Exception:
            pass

    # Estimate cost (rough approximation for Claude models)
    # Input: ~$3/MTok, Output: ~$15/MTok (claude-3-sonnet ballpark)
    estimated_cost = (total_input_tokens * 3 + total_output_tokens * 15) / 1_000_000

    return {
        "id": session_uuid,
        "short_id": short_id,
        "cwd": cwd,
        "start_time": start_time,
        "end_time": end_time,
        "duration_secs": duration_secs,
        "task": first_user_text or "(no task description)",
        "tool_calls": tool_calls,
        "files_touched": sorted(files_touched),
        "models_used": sorted(models_used),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cache_tokens": total_cache_tokens,
        "total_tokens": total_input_tokens + total_output_tokens,
        "estimated_cost": estimated_cost,
        "message_count": len(messages)
    }


def _find_session_by_id(sessions: list, run_id: str) -> Optional[dict]:
    """Find a session by short or full ID."""
    for s in sessions:
        if s["id"] == run_id or s["short_id"] == run_id or s["id"].startswith(run_id):
            return s
    return None


def _format_duration(secs: Optional[float]) -> str:
    if secs is None:
        return "?"
    secs = int(secs)
    if secs < 60:
        return f"{secs}s"
    m, s = divmod(secs, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def _format_time(ts) -> str:
    if ts is None:
        return "?"
    try:
        from datetime import datetime
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts)
        else:
            for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    dt = datetime.strptime(ts, fmt)
                    break
                except Exception:
                    continue
            else:
                return str(ts)[:16]
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)[:16]


def _format_list(sessions: list) -> str:
    if not sessions:
        return "No agent runs found."
    lines = []
    for s in sessions:
        model = s["models_used"][0] if s["models_used"] else "unknown"
        lines.append(f"  {s['short_id']}  {_format_time(s['start_time'])}  {s['task'][:50]}")
        lines.append(
            f"            {len(s['tool_calls'])} calls  {len(s['files_touched'])} files  "
            f"{_format_duration(s['duration_secs'])}  {model}  "
            f"{s['total_tokens']:,} tok  ~${s['estimated_cost']:.4f}"
        )
        lines.append("")
    return "\n".join(lines)


def _format_show(s: dict) -> str:
    model = s["models_used"][0] if s["models_used"] else "unknown"
    lines = [
        f"  run      {s['short_id']}",
        f"  task     {s['task']}",
        f"  date     {_format_time(s['start_time'])}",
        f"  duration {_format_duration(s['duration_secs'])}",
        f"  model    {model}",
        f"  tokens   in={s['total_input_tokens']:,}  out={s['total_output_tokens']:,}  cache={s['total_cache_tokens']:,}  ~${s['estimated_cost']:.4f}",
        "",
        "  files touched:",
    ]
    for f in s["files_touched"]:
        lines.append(f"  M  {f}")
    if not s["files_touched"]:
        lines.append("  (none)")
    lines.append("")
    lines.append("  tool calls:")
    for i, call in enumerate(s["tool_calls"]):
        tool = call["tool"]
        detail = ""
        if "file" in call:
            detail = call["file"]
        elif "command" in call:
            detail = f"$ {call['command'][:60]}"
        lines.append(f"  {i:02d}  {tool:<8} {detail}")
    if not s["tool_calls"]:
        lines.append("  (none)")
    return "\n".join(lines)


def _format_diff(a: dict, b: dict) -> str:
    def truncate(s, n):
        return s[:n] if len(s) > n else s

    col_w = 45
    sep = " │ "
    lines = []

    a_header = f"{a['short_id']}  {truncate(a['task'], 25)}"
    b_header = f"{b['short_id']}  {truncate(b['task'], 25)}"
    lines.append(f"  {a_header:<{col_w}}{sep}{b_header}")

    a_meta = f"{_format_time(a['start_time'])}  {len(a['tool_calls'])} calls  {_format_duration(a['duration_secs'])}"
    b_meta = f"{_format_time(b['start_time'])}  {len(b['tool_calls'])} calls  {_format_duration(b['duration_secs'])}"
    lines.append(f"  {a_meta:<{col_w}}{sep}{b_meta}")
    lines.append("  " + "-" * col_w + "-+-" + "-" * col_w)
    lines.append("  tool calls")

    a_calls = a["tool_calls"]
    b_calls = b["tool_calls"]
    max_len = max(len(a_calls), len(b_calls))

    for i in range(max_len):
        a_call = a_calls[i] if i < len(a_calls) else None
        b_call = b_calls[i] if i < len(b_calls) else None

        def fmt_call(c, idx):
            if c is None:
                return ""
            tool = c["tool"]
            detail = c.get("file") or (f"$ {c['command'][:30]}" if "command" in c else "")
            return f"{idx:02d} {tool:<8} {detail}"

        a_str = fmt_call(a_call, i)
        b_str = fmt_call(b_call, i)

        prefix = "  "
        if a_call and b_call:
            if a_call["tool"] == b_call["tool"]:
                prefix = "= "
            else:
                prefix = "~ "
        elif a_call and not b_call:
            prefix = "- "
        elif b_call and not a_call:
            prefix = "+ "

        lines.append(f"  {prefix}{a_str:<{col_w}}{sep}{b_str}")

    lines.append("  " + "-" * col_w + "-+-" + "-" * col_w)
    lines.append("  files touched")

    a_files = set(a["files_touched"])
    b_files = set(b["files_touched"])
    all_files = sorted(a_files | b_files)
    for f in all_files:
        in_a = f in a_files
        in_b = f in b_files
        prefix = "= " if in_a and in_b else ("- " if in_a else "+ ")
        a_str = f if in_a else ""
        b_str = f if in_b else ""
        lines.append(f"  {prefix}{a_str:<{col_w}}{sep}{b_str}")

    return "\n".join(lines)


def _format_stats(sessions: list) -> str:
    if not sessions:
        return "No agent runs found."

    total_cost = sum(s["estimated_cost"] for s in sessions)
    total_tokens = sum(s["total_tokens"] for s in sessions)
    total_duration = sum(s["duration_secs"] or 0 for s in sessions)
    avg_cost = total_cost / len(sessions) if sessions else 0

    file_counts: dict = {}
    for s in sessions:
        for f in s["files_touched"]:
            file_counts[f] = file_counts.get(f, 0) + 1

    model_counts: dict = {}
    for s in sessions:
        for m in s["models_used"]:
            model_counts[m] = model_counts.get(m, 0) + 1

    top_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    lines = [
        f"  total runs     {len(sessions)}",
        f"  total cost     ~${total_cost:.4f}",
        f"  avg cost/run   ~${avg_cost:.4f}",
        f"  total tokens   {total_tokens:,}",
        f"  total time     {_format_duration(total_duration)}",
        "",
        "  most-touched files:",
    ]
    for f, count in top_files:
        lines.append(f"  {count:3d}x  {f}")
    if not top_files:
        lines.append("  (none)")

    lines.append("")
    lines.append("  model usage:")
    for model, count in sorted(model_counts.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"  {count:3d}x  {model}")
    if not model_counts:
        lines.append("  (none)")

    return "\n".join(lines)


@mcp.tool()
async def list_runs(
    limit: int = 20,
    all_projects: bool = False
) -> dict:
    """List recent Claude Code agent runs in git log style. Use this as the default starting point to see what agent sessions have been run, their costs, token usage, duration, and which files were touched. Shows runs associated with the current working directory."""
    args = []
    if limit != 20:
        args += ["--limit", str(limit)]
    if all_projects:
        args += ["--all"]

    # Try ferretlog CLI first
    result = subprocess.run(
        ["ferretlog"] + args,
        capture_output=True, text=True, timeout=30
    ) if _ferretlog_available() else None

    if result and result.returncode == 0 and result.stdout:
        return {
            "success": True,
            "output": result.stdout,
            "source": "ferretlog_cli"
        }

    # Fallback: read logs directly
    data = _read_claude_logs_directly(args)
    data["source"] = "direct_read"
    return data


@mcp.tool()
async def show_run(run_id: str) -> dict:
    """Show the full tool-by-tool breakdown of a specific agent run. Use this when you want to understand exactly what the agent did step-by-step: which files it read, what bash commands it ran, what edits it made, and the token/cost details. Requires a run ID from list_runs."""
    args = ["show", run_id]

    if _ferretlog_available():
        try:
            result = subprocess.run(
                ["ferretlog"] + args,
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0 and result.stdout:
                return {
                    "success": True,
                    "output": result.stdout,
                    "source": "ferretlog_cli"
                }
        except Exception:
            pass

    # Fallback
    data = _read_claude_logs_directly(args)
    data["source"] = "direct_read"
    return data


@mcp.tool()
async def diff_runs(run_id_a: str, run_id_b: str) -> dict:
    """Compare two agent runs side-by-side to see how they differed. Use this when the same or similar task was run multiple times and you want to understand why they went differently — different tool call sequences, files touched, costs, or durations."""
    args = ["diff", run_id_a, run_id_b]

    if _ferretlog_available():
        try:
            result = subprocess.run(
                ["ferretlog"] + args,
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0 and result.stdout:
                return {
                    "success": True,
                    "output": result.stdout,
                    "source": "ferretlog_cli"
                }
        except Exception:
            pass

    # Fallback
    data = _read_claude_logs_directly(args)
    data["source"] = "direct_read"
    return data


@mcp.tool()
async def get_stats(all_projects: bool = False) -> dict:
    """Show aggregate statistics across all agent runs: total cost, total tokens consumed, total time spent, average run cost, most-touched files, and model usage breakdown. Use this to understand overall Claude Code usage patterns and spending."""
    args = ["stats"]
    if all_projects:
        args += ["--all"]

    if _ferretlog_available():
        try:
            result = subprocess.run(
                ["ferretlog"] + args,
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0 and result.stdout:
                return {
                    "success": True,
                    "output": result.stdout,
                    "source": "ferretlog_cli"
                }
        except Exception:
            pass

    # Fallback
    data = _read_claude_logs_directly(args)
    data["source"] = "direct_read"
    return data


def _ferretlog_available() -> bool:
    """Check if the ferretlog CLI is available."""
    try:
        result = subprocess.run(
            ["ferretlog", "--help"],
            capture_output=True, text=True, timeout=5
        )
        return True
    except (FileNotFoundError, Exception):
        return False




async def health(request):
    return JSONResponse({"status": "ok", "server": mcp.name})

async def tools(request):
    registered = await mcp.list_tools()
    tool_list = [{"name": t.name, "description": t.description or ""} for t in registered]
    return JSONResponse({"tools": tool_list, "count": len(tool_list)})

mcp_app = mcp.http_app(transport="streamable-http", stateless_http=True)

class _FixAcceptHeader:
    """Ensure Accept header includes both types FastMCP requires."""
    def __init__(self, app):
        self.app = app
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            accept = headers.get(b"accept", b"").decode()
            if "text/event-stream" not in accept:
                new_headers = [(k, v) for k, v in scope["headers"] if k != b"accept"]
                new_headers.append((b"accept", b"application/json, text/event-stream"))
                scope = dict(scope, headers=new_headers)
        await self.app(scope, receive, send)

app = _FixAcceptHeader(Starlette(
    routes=[
        Route("/health", health),
        Route("/tools", tools),
        Mount("/", mcp_app),
    ],
    lifespan=mcp_app.lifespan,
))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
