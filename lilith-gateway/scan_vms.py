#!/usr/bin/env python3
"""Scan libvirt for VMs and write vms.json"""
import json, subprocess, os, shutil
from pathlib import Path
from datetime import datetime

def run_virsh(*args):
    try:
        result = subprocess.run(["virsh"] + list(args), capture_output=True, text=True, timeout=10)
        return result.stdout.strip(), result.returncode
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "", -1

vms = []

# Check libvirt available
virsh_path = shutil.which("virsh")
if virsh_path:
    output, rc = run_virsh("list", "--all")
    if rc == 0:
        for line in output.split("\n")[2:]:  # Skip header
            parts = line.strip().split(None, 2)
            if len(parts) >= 3:
                vm_id, state, name = parts[0], parts[2], parts[1]
                # Get more info
                info_out, _ = run_virsh("dominfo", name)
                vcpu = ""; memory = ""; autostart = ""
                for iline in info_out.split("\n"):
                    if "CPU(s):" in iline: vcpu = iline.split(":")[1].strip()
                    if "Max memory:" in iline: memory = iline.split(":")[1].strip()
                    if "Autostart:" in iline: autostart = iline.split(":")[1].strip()
                
                # Get IP if running
                ip_addr = ""
                if "running" in state.lower():
                    ip_out, _ = run_virsh("domifaddr", name, "--source", "agent")
                    for iline in ip_out.split("\n"):
                        if "ipv4" in iline:
                            ip_addr = iline.strip().split()[-1]
                            break
                
                vms.append({
                    "name": name,
                    "state": state,
                    "vcpu": vcpu,
                    "memory": memory,
                    "autostart": autostart == "enable",
                    "ip": ip_addr,
                    "id": vm_id,
                })
    else:
        # libvirtd might not be running
        pass
else:
    print("virsh not found — skipping VM scan")

output = {
    "vms": vms,
    "count": len(vms),
    "virsh_available": virsh_path is not None,
    "generated": datetime.now().isoformat(),
}

GATEWAY = os.path.dirname(os.path.abspath(__file__))
Path(os.path.join(GATEWAY, "vms.json")).write_text(json.dumps(output, indent=2))
print(f"Scanned {len(vms)} VMs → vms.json")
for vm in vms:
    print(f"  {vm['name']}: {vm['state']} ({vm['vcpu']} vCPU, {vm['memory']})")
