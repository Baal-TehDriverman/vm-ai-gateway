"""
winrm_client.py — Remote Windows PowerShell execution via WinRM.
Uses evil-winrm if available, or falls back to instructing the user.
"""

import asyncio
import shutil
import subprocess
import re
from typing import Optional


def _evil_winrm_available() -> bool:
    return shutil.which("evil-winrm") is not None


async def execute_powershell(
    command: str,
    host: str = "localhost",
    port: int = 5985,
    username: str = "",
    password: str = "",
) -> dict:
    """
    Execute a PowerShell command on the Windows VM via WinRM.
    Uses evil-winrm for authenticated WinRM access.
    """
    if not _evil_winrm_available():
        return {
            "success": False,
            "error": "evil-winrm is not installed. Install it with:\n"
                     "  sudo gem install evil-winrm\n"
                     "Or use ruby:\n"
                     "  gem install evil-winrm\n"
                     "Then configure WinRM in the Windows VM (see WINDOWS_VM_SETUP_GUIDE.md)",
            "command": command,
        }

    if not username:
        return {
            "success": False,
            "error": "Windows username not configured. Set it in the dashboard settings.",
            "command": command,
        }

    # Build evil-winrm command
    cmd = [
        "evil-winrm",
        "-i", host,
        "-P", str(port),
        "-u", username,
    ]

    # Use password file for security
    import tempfile
    import os
    if password:
        pw_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".pw")
        pw_file.write(password)
        pw_file.close()
        cmd.extend(["-p", pw_file.name])

    # Command to execute
    cmd.extend(["-c", command])

    try:
        r = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=60,
        )

        # Clean up password file
        if password:
            os.unlink(pw_file.name)

        # Parse output to remove evil-winrm banner
        output = r.stdout
        # Skip the evil-winrm banner
        lines = output.split("\n")
        clean_lines = []
        in_banner = False
        for line in lines:
            if "Evil-WinRM" in line and "PS" not in line:
                in_banner = True
                continue
            if in_banner and line.strip().startswith("PS"):
                in_banner = False
            if not in_banner:
                clean_lines.append(line)

        return {
            "success": r.returncode == 0,
            "stdout": "\n".join(clean_lines).strip(),
            "stderr": r.stderr.strip(),
            "returncode": r.returncode,
            "command": command,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Command timed out (60s)",
            "command": command,
        }
    except Exception as e:
        if password:
            try:
                os.unlink(pw_file.name)
            except Exception:
                pass
        return {
            "success": False,
            "error": str(e),
            "command": command,
        }


async def check_connection(username: str = "", password: str = "") -> dict:
    """Test WinRM connection to the VM."""
    return await execute_powershell("Get-ChildItem Env: | Select-Object -First 5", username=username, password=password)


def get_winrm_setup_instructions() -> str:
    """Return instructions for setting up WinRM in the Windows VM."""
    return """# WinRM Setup Instructions (run in ADMIN PowerShell in the VM):

# 1. Enable PowerShell Remoting
Enable-PSRemoting -Force

# 2. Allow all hosts (development only)
Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value "*" -Force

# 3. Allow WinRM through firewall
New-NetFirewallRule -DisplayName "WinRM HTTP" -Direction Inbound `
    -Protocol TCP -LocalPort 5985 -Action Allow

# 4. Enable WinRM auto-start
Set-Service WinRM -StartupType Automatic

# 5. Verify
Get-ChildItem WSMan:\\localhost\\listener
Test-WSMan

# From Linux host, verify with:
# evil-winrm -i localhost -u YOUR_USERNAME -p YOUR_PASSWORD
"""
