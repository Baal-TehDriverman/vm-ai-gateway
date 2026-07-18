#!/usr/bin/env python3
"""
Windows Port Console — AI-Powered Cross-Platform Development Dashboard

A web-based GUI for managing a Windows 11 VM, writing code in the browser,
and porting software between Windows and Linux via remote compilation.

Usage:
  python3 server.py
  # Opens at http://localhost:8080
"""

import asyncio
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Query
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from vm_manager import (
    get_status, start_vm, stop_vm, take_screenshot,
    create_vm, get_iso_info, VM_NAME, ISO_PATH,
)
from winrm_client import execute_powershell, check_connection, get_winrm_setup_instructions

app = FastAPI(title="Windows Port Console", version="1.0.0")

SHARED_DIR = Path.home() / "Desktop" / "cross-compile"
SHARED_DIR.mkdir(exist_ok=True)

# ─── VM Management API ───────────────────────────────────────────────


@app.get("/api/vm/status")
async def api_vm_status():
    status = await get_status()
    iso = await get_iso_info()
    status["iso"] = iso
    return status


@app.post("/api/vm/start")
async def api_vm_start(headless: bool = Query(True)):
    return await start_vm(headless=headless)


@app.post("/api/vm/stop")
async def api_vm_stop(force: bool = Query(False)):
    return await stop_vm(force=force)


@app.post("/api/vm/screenshot")
async def api_vm_screenshot():
    result = await take_screenshot()
    if result.get("success") and os.path.exists(result["path"]):
        return FileResponse(result["path"], media_type="image/png")
    return JSONResponse(status_code=503, content=result)


@app.post("/api/vm/create")
async def api_vm_create():
    return await create_vm()


@app.get("/api/vm/iso")
async def api_vm_iso():
    return await get_iso_info()

# ─── WinRM / PowerShell API ─────────────────────────────────────────


@app.post("/api/winrm/execute")
async def api_winrm_execute(
    command: str = Form(...),
    username: str = Form(""),
    password: str = Form(""),
    host: str = Form("localhost"),
    port: int = Form(5985),
):
    result = await execute_powershell(command, host, port, username, password)
    return result


@app.post("/api/winrm/check")
async def api_winrm_check(
    username: str = Form(""),
    password: str = Form(""),
):
    return await check_connection(username, password)


@app.get("/api/winrm/setup-guide")
async def api_winrm_guide():
    return {"guide": get_winrm_setup_instructions()}

# ─── File Transfer API ────────────────────────────────────────────────


@app.get("/api/files/list")
async def api_files_list(path: str = "."):
    """List files in the shared directory or a subdirectory."""
    target = (SHARED_DIR / path).resolve()
    if not str(target).startswith(str(SHARED_DIR.resolve())):
        return {"error": "Path outside shared directory"}
    if not target.exists():
        return {"error": "Path does not exist", "files": []}

    files = []
    for f in sorted(target.iterdir()):
        files.append({
            "name": f.name,
            "path": str(f.relative_to(SHARED_DIR)),
            "is_dir": f.is_dir(),
            "size": f.stat().st_size if f.is_file() else 0,
            "modified": f.stat().st_mtime,
        })
    return {"files": files, "current_path": path}


@app.post("/api/files/upload")
async def api_files_upload(file: UploadFile = File(...), path: str = Form(".")):
    """Upload a file to the shared directory."""
    target_dir = (SHARED_DIR / path).resolve()
    if not str(target_dir).startswith(str(SHARED_DIR.resolve())):
        return {"error": "Path outside shared directory"}
    target_dir.mkdir(parents=True, exist_ok=True)

    target_file = target_dir / file.filename
    content = await file.read()
    target_file.write_bytes(content)

    return {
        "success": True,
        "filename": file.filename,
        "size": len(content),
        "path": str(target_file.relative_to(SHARED_DIR)),
    }


@app.get("/api/files/download")
async def api_files_download(path: str = Query(...)):
    """Download a file from the shared directory."""
    target = (SHARED_DIR / path).resolve()
    if not str(target).startswith(str(SHARED_DIR.resolve())):
        return {"error": "Path outside shared directory"}
    if not target.exists() or target.is_dir():
        return {"error": "File not found"}
    return FileResponse(str(target))


@app.post("/api/files/delete")
async def api_files_delete(path: str = Form(...)):
    """Delete a file or directory in the shared directory."""
    target = (SHARED_DIR / path).resolve()
    if not str(target).startswith(str(SHARED_DIR.resolve())):
        return {"error": "Path outside shared directory"}
    if target.is_file():
        target.unlink()
    elif target.is_dir():
        import shutil
        shutil.rmtree(str(target))
    else:
        return {"error": "Not found"}
    return {"success": True}


@app.post("/api/files/write")
async def api_files_write(path: str = Form(...), content: str = Form(...)):
    """Write content to a file in the shared directory."""
    target = (SHARED_DIR / path).resolve()
    if not str(target).startswith(str(SHARED_DIR.resolve())):
        return {"error": "Path outside shared directory"}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return {"success": True, "path": path, "size": len(content)}


@app.get("/api/files/read")
async def api_files_read(path: str = Query(...)):
    """Read a file's content from the shared directory."""
    target = (SHARED_DIR / path).resolve()
    if not str(target).startswith(str(SHARED_DIR.resolve())):
        return {"error": "Path outside shared directory"}
    if not target.exists() or target.is_dir():
        return {"error": "File not found"}
    content = target.read_text(encoding="utf-8", errors="replace")
    return {"content": content, "path": path}

# ─── AI Assistance API ────────────────────────────────────────────────


@app.post("/api/ai/port")
async def api_ai_port(request: dict):
    """
    AI-powered code porting assistance.
    Takes source code and target platform, returns porting suggestions.
    Uses local analysis (no external API calls) for basic porting hints.
    """
    source_code = request.get("code", "")
    source_lang = request.get("source_lang", "")
    target_lang = request.get("target_lang", "")

    if not source_code:
        return {"error": "No code provided"}

    # Basic heuristic-based porting analysis
    analysis = analyze_port(source_code, source_lang, target_lang)
    return analysis


def analyze_port(code: str, source_lang: str, target_lang: str) -> dict:
    """Analyze code for porting between Windows and Linux."""
    lines = code.split("\n")
    total_lines = len(lines)

    issues = []
    suggestions = []
    windows_patterns = []
    linux_patterns = []

    # Windows-specific patterns
    win_patterns = {
        r"(?i)#include\s*<windows\.h>": "Windows API header — needs Linux equivalent",
        r"(?i)#include\s*<winsock": "Windows Sockets — use standard POSIX sockets or port to BSD sockets",
        r"(?i)CreateFile[WA]?": "Windows CreateFile API — use open()/fopen() on Linux",
        r"(?i)WriteFile|ReadFile": "Windows file I/O — use POSIX read()/write()",
        r"(?i)Reg(Open|Create|Close|Query|Set)": "Windows Registry API — use config files on Linux",
        r"(?i)CoInitialize|COM|OleInitialize": "COM initialization — not available on Linux",
        r"(?i)GetProcAddress|LoadLibrary": "Dynamic loading — use dlopen()/dlsym() on Linux",
        r"(?i)MessageBox[WA]?": "Windows MessageBox — use GTK/Qt/terminal on Linux",
        r"(?i)TCHAR|_T\s*\(": "Windows TCHAR — use plain char on Linux",
        r"(?i)LPCSTR|LPWSTR|LPTSTR|LPCWSTR": "Windows string types — use standard C types on Linux",
        r"(?i)HANDLE": "Windows HANDLE — use int fd on Linux",
        r"(?i)DWORD|LONG|UINT|BOOL": "Windows typedefs — define equivalents or use stdint.h",
        r"(?i)\\r\\n": "Windows CRLF line endings — use LF on Linux",
        r"(?i)Sleep\s*\(": "Windows Sleep(milliseconds) — use usleep() or nanosleep() on Linux",
        r"(?i)GetSystemInfo|GetComputerName|GetVersion": "Windows system info — use uname()/sysinfo()",
        r"(?i)WSADATA|WSAStartup|WSACleanup": "Winsock startup — not needed on Linux",
        r"(?i)SOCKET": "Windows SOCKET — use int fd on Linux",
        r"(?i)closesocket": "Windows socket close — use close() on Linux",
        r"(?i)__declspec|__cdecl|__stdcall": "Windows calling conventions — not needed on Linux",
        r"(?i)#pragma\s+comment\s*\(\s*lib": "Pragma library linking — use Makefile/CMake on Linux",
    }

    # Linux/POSIX patterns (things that work already)
    linux_patterns_list = {
        r"(?i)#include\s*<stdio\.h>": "Standard I/O — portable",
        r"(?i)#include\s*<stdlib\.h>": "Standard library — portable",
        r"(?i)#include\s*<string\.h>": "String functions — portable",
        r"(?i)#include\s*<math\.h>": "Math library — portable",
        r"(?i)#include\s*<unistd\.h>": "POSIX API — already Linux-compatible",
        r"(?i)#include\s*<pthread": "POSIX threads — portable to Linux",
        r"(?i)#include\s*<sys/socket": "BSD sockets — portable to Linux",
        r"(?i)#include\s*<fcntl\.h>": "File control — portable",
    }

    import re
    for pattern, desc in win_patterns.items():
        matches = [(i + 1, line) for i, line in enumerate(lines) if re.search(pattern, line)]
        if matches:
            windows_patterns.append({
                "description": desc,
                "pattern": pattern,
                "occurrences": [{"line": m[0], "text": m[1].strip()} for m in matches[:5]],
            })

    for pattern, desc in linux_patterns_list.items():
        matches = [(i + 1, line) for i, line in enumerate(lines) if re.search(pattern, line)]
        if matches:
            linux_patterns.append({
                "description": desc,
                "matches": len(matches),
            })

    # Build suggestions based on findings
    if windows_patterns:
        suggestions.append({
            "category": "API Translation",
            "items": [p["description"] for p in windows_patterns[:8]],
        })

    # Check file extension for language detection
    ext = os.path.splitext(source_lang)[1].lower() if source_lang else ""

    if ext in [".cs", ".vb", ".fs"]:
        suggestions.append({
            "category": "Runtime",
            "items": [
                "C#/.NET code requires Mono or .NET Runtime on Linux",
                "Install mono-complete: sudo pacman -S mono",
                "Or use .NET Core which is cross-platform by design",
            ],
        })
    elif ext in [".cpp", ".c", ".h", ".hpp"]:
        suggestions.append({
            "category": "Build System",
            "items": [
                "Use CMake for cross-platform builds",
                "Or provide a Makefile with platform conditionals",
                "GCC/Clang are recommended compilers on Linux",
            ],
        })
    elif ext in [".py"]:
        suggestions.append({
            "category": "Python Portability",
            "items": [
                "Python is already cross-platform",
                "Check for os.name == 'nt' conditionals",
                "Use pathlib instead of os.path for portable paths",
                r"Replace \ with os.sep or Path('/')",
            ],
        })

    return {
        "total_lines": total_lines,
        "windows_patterns_found": len(windows_patterns),
        "linux_standard_patterns": len(linux_patterns),
        "windows_patterns": windows_patterns[:10],
        "linux_patterns": linux_patterns[:10],
        "suggestions": suggestions,
        "portability_score": max(0, min(100,
            100 - (len(windows_patterns) * 15) +
            (len(linux_patterns) * 5)
        )),
    }

# ─── WebSocket Terminal ──────────────────────────────────────────────


@app.websocket("/ws/terminal")
async def websocket_terminal(websocket: WebSocket):
    """WebSocket-based terminal for executing commands on the host."""
    await websocket.accept()
    await websocket.send_text(json.dumps({
        "type": "banner",
        "message": "Windows Port Console — Host Terminal (Linux)",
        "prompt": f"{os.environ.get('USER', 'user')}@host:~$ ",
    }))

    process = None

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "command":
                cmd = msg.get("command", "")

                if cmd.strip().lower() == "exit":
                    await websocket.send_text(json.dumps({
                        "type": "output",
                        "data": "Terminal closed.",
                    }))
                    break

                # Execute the command
                try:
                    r = subprocess.run(
                        cmd,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=30,
                        executable="/bin/bash",
                    )
                    output = r.stdout + r.stderr
                    if not output:
                        output = f"Command completed (exit code: {r.returncode})"

                    await websocket.send_text(json.dumps({
                        "type": "output",
                        "data": output,
                        "returncode": r.returncode,
                    }))
                except subprocess.TimeoutExpired:
                    await websocket.send_text(json.dumps({
                        "type": "output",
                        "data": "Command timed out (30s)",
                    }))
                except Exception as e:
                    await websocket.send_text(json.dumps({
                        "type": "output",
                        "data": f"Error: {e}",
                    }))

    except WebSocketDisconnect:
        pass
    finally:
        if process:
            process.terminate()

# ─── Serve Frontend ──────────────────────────────────────────────────


@app.get("/")
async def index():
    html = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html.read_text(encoding="utf-8"))


@app.get("/app.js")
async def app_js():
    js = Path(__file__).parent / "static" / "app.js"
    return HTMLResponse(js.read_text(encoding="utf-8"), media_type="application/javascript")


@app.get("/style.css")
async def style_css():
    css = Path(__file__).parent / "static" / "style.css"
    return HTMLResponse(css.read_text(encoding="utf-8"), media_type="text/css")


# ─── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("""
  ╔══════════════════════════════════════════════════════╗
  ║      Windows Port Console — AI Dev Dashboard         ║
  ║                                                      ║
  ║  Manage your Windows 11 VM, write code in the        ║
  ║  browser, and port software between Windows & Linux  ║
  ║                                                      ║
  ║  Open:  http://localhost:8081                        ║
  ║  Quit:  Ctrl+C                                       ║
  ╚══════════════════════════════════════════════════════╝
    """)
    uvicorn.run(app, host="0.0.0.0", port=8081)
