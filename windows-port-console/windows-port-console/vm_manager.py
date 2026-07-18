"""
vm_manager.py — VirtualBox VM lifecycle management
Gracefully degrades if VirtualBox is not installed.
"""

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

VM_NAME = "Windows 11 Console"
ISO_PATH = str(Path.home() / "Desktop" / "Win11_Enterprise_Eval.iso")
VM_DIR = str(Path.home() / "Desktop" / "Windows 11 Console")
VDI_PATH = str(Path.home() / "Desktop" / "Windows 11 Console" / "disk.vdi")


def _vbox_available() -> bool:
    return shutil.which("VBoxManage") is not None


def _run_vbox(args: list[str]) -> dict:
    if not _vbox_available():
        return {
            "success": False,
            "error": "VirtualBox (VBoxManage) is not installed. Install it with:\n"
                     "  sudo pacman -S virtualbox virtualbox-ext-oracle\n"
                     "  sudo modprobe vboxdrv\n"
                     "  sudo usermod -aG vboxusers $USER\n"
                     "Then log out and back in.",
        }
    try:
        r = subprocess.run(
            ["VBoxManage"] + args,
            capture_output=True, text=True, timeout=30,
        )
        return {
            "success": r.returncode == 0,
            "stdout": r.stdout.strip(),
            "stderr": r.stderr.strip(),
            "returncode": r.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "VBoxManage command timed out"}
    except FileNotFoundError:
        return {"success": False, "error": "VBoxManage not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_status() -> dict:
    """Get detailed VM status."""
    r = _run_vbox(["showvminfo", VM_NAME, "--machinereadable"])
    if not r["success"]:
        if "Could not find a registered machine" in r.get("stderr", ""):
            return {"state": "not_created", "vbox_installed": _vbox_available()}
        return {"state": "error", "error": r.get("stderr", r.get("error", "Unknown")),
                "vbox_installed": _vbox_available()}

    info = {}
    for line in r["stdout"].split("\n"):
        if "=" in line:
            k, v = line.split("=", 1)
            info[k.strip()] = v.strip().strip('"')

    vm_state = info.get("VMState", "unknown")
    state_map = {
        "running": "running",
        "poweroff": "stopped",
        "saved": "saved",
        "aborted": "aborted",
        "paused": "paused",
    }
    return {
        "state": state_map.get(vm_state, vm_state),
        "name": info.get("name", VM_NAME),
        "memory": info.get("memory", "unknown"),
        "cpus": info.get("cpus", "unknown"),
        "vram": info.get("vram", "unknown"),
        "ostype": info.get("ostype", "unknown"),
        "vbox_installed": True,
        "raw_state": vm_state,
        "ip": _get_guest_ip(info),
    }


def _get_guest_ip(info: dict) -> Optional[str]:
    """Get IP from guest properties."""
    for key in [
        "/VirtualBox/GuestInfo/Net/0/V4/IP",
        "/VirtualBox/GuestInfo/Net/1/V4/IP",
    ]:
        val = info.get(key)
        if val and val != "0.0.0.0" and val != "":
            return val
    return None


async def start_vm(headless: bool = True) -> dict:
    """Start the VM."""
    if headless:
        r = _run_vbox(["startvm", VM_NAME, "--type", "headless"])
    else:
        r = _run_vbox(["startvm", VM_NAME])
    if r["success"]:
        await asyncio.sleep(3)
    return r


async def stop_vm(force: bool = False) -> dict:
    """Stop the VM gracefully (ACPI) or forcefully."""
    if force:
        return _run_vbox(["controlvm", VM_NAME, "poweroff"])
    return _run_vbox(["controlvm", VM_NAME, "acpipowerbutton"])


async def take_screenshot() -> dict:
    """Take a screenshot and return the path."""
    path = f"/tmp/windows_vm_screenshot.png"
    r = _run_vbox(["controlvm", VM_NAME, "screenshotpng", path])
    if r["success"] and os.path.exists(path):
        return {"success": True, "path": path, "size": os.path.getsize(path)}
    return r


async def create_vm() -> dict:
    """Create the VM with sensible defaults."""
    if not _vbox_available():
        return {"success": False, "error": "VBoxManage not installed"}

    # Check if already exists
    r = _run_vbox(["showvminfo", VM_NAME])
    if r["success"]:
        return {"success": True, "message": "VM already exists"}

    os.makedirs(VM_DIR, exist_ok=True)

    steps = [
        (["createvm", "--name", VM_NAME, "--ostype", "Windows11_64",
          "--basefolder", str(Path(VM_DIR).parent), "--register"],
         "Create VM"),
        (["modifyvm", VM_NAME, "--memory", "8192"], "Set RAM (8 GB)"),
        (["modifyvm", VM_NAME, "--cpus", "2"], "Set vCPUs (2)"),
        (["modifyvm", VM_NAME, "--pae", "on"], "Enable PAE"),
        (["modifyvm", VM_NAME, "--vram", "128"], "Set VRAM (128 MB)"),
        (["modifyvm", VM_NAME, "--graphicscontroller", "vmsvga"], "Graphics controller"),
        (["modifyvm", VM_NAME, "--accelerate3d", "on"], "Enable 3D acceleration"),
        (["modifyvm", VM_NAME, "--firmware", "efi64"], "Enable EFI"),
        (["modifyvm", VM_NAME, "--chipset", "ich9"], "Chipset ICH9"),
        (["modifyvm", VM_NAME, "--audio", "pulse", "--audioout", "on"], "Audio"),
        (["modifyvm", VM_NAME, "--clipboard", "bidirectional"], "Clipboard"),
        (["modifyvm", VM_NAME, "--draganddrop", "bidirectional"], "Drag & drop"),
        (["modifyvm", VM_NAME, "--nic1", "nat"], "NIC NAT"),
        (["modifyvm", VM_NAME, "--natpf1", "rdp,tcp,,3389,,3389"], "Port forward RDP"),
        (["modifyvm", VM_NAME, "--natpf1", "winrm-http,tcp,,5985,,5985"], "Port forward WinRM HTTP"),
        (["modifyvm", VM_NAME, "--natpf1", "winrm-https,tcp,,5986,,5986"], "Port forward WinRM HTTPS"),
        (["createmedium", "disk", "--filename", VDI_PATH,
          "--size", "81920", "--format", "VDI"], "Create disk (80 GB)"),
        (["storagectl", VM_NAME, "--name", "SATA", "--add", "sata", "--controller", "IntelAhci"],
         "Add SATA controller"),
        (["storageattach", VM_NAME, "--storagectl", "SATA",
          "--port", "0", "--device", "0", "--type", "hdd", "--medium", VDI_PATH],
         "Attach disk"),
    ]

    # Add storage controller for DVD
    steps.append(
        (["storagectl", VM_NAME, "--name", "IDE", "--add", "ide", "--controller", "PIIX4"],
         "Add IDE controller for DVD")
    )

    # Attach ISO if exists
    if os.path.exists(ISO_PATH):
        steps.append(
            (["storageattach", VM_NAME, "--storagectl", "IDE",
              "--port", "0", "--device", "0", "--type", "dvddrive",
              "--medium", ISO_PATH],
             "Attach ISO"),
        )

    errors = []
    for args, desc in steps:
        result = _run_vbox(args)
        if not result["success"]:
            errors.append(f"{desc}: {result.get('stderr', result.get('error', 'unknown'))}")

    if errors:
        return {"success": False, "errors": errors}

    return {"success": True, "message": "VM created successfully"}


async def get_ip() -> Optional[str]:
    """Try to get VM IP from guest properties."""
    r = _run_vbox(["guestproperty", "get", VM_NAME,
                    "/VirtualBox/GuestInfo/Net/0/V4/IP"])
    if r["success"]:
        val = r["stdout"].replace("Value: ", "").strip()
        if val != "0.0.0.0" and val:
            return val
    return None


async def get_iso_info() -> dict:
    """Get info about the downloaded ISO."""
    if not os.path.exists(ISO_PATH):
        return {"exists": False, "path": ISO_PATH}
    size = os.path.getsize(ISO_PATH)
    return {
        "exists": True,
        "path": ISO_PATH,
        "size_gb": round(size / (1024**3), 2),
    }
