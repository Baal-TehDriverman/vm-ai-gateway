#!/usr/bin/env python3
"""
Lilith Unified Dashboard - Desktop Launcher Generator
Creates .desktop files for easy application launching
"""

import os
import json
from pathlib import Path

# Desktop entries configuration
DESKTOP_ENTRIES = [
    {
        "name": "Lilith Unified Dashboard",
        "exec": "bash -c 'cd /home/tehlappy/Projects/UnifiedDashboard && ./start.sh'",
        "icon": "/home/tehlappy/Projects/UnifiedDashboard/public/icon.png",
        "categories": "Development;IDE;",
        "comment": "Unified Developer Dashboard - Lilith Gateway + GitHub Intelligence + Kairos Dream",
        "terminal": True,
        "startupNotify": True,
    },
    {
        "name": "Lilith Gateway",
        "exec": "bash -c 'cd /home/tehlappy/Projects/Dev Console/vm-ai-gateway/lilith-gateway && python3 gateway_server.py'",
        "icon": "/home/tehlappy/Projects/Dev Console/vm-ai-gateway/lilith-gateway/static/icon.png",
        "categories": "System;Network;",
        "comment": "Lilith Gateway Control Plane - Apps, VMs, LLM Proxy",
        "terminal": True,
        "startupNotify": True,
    },
    {
        "name": "BlackSpace Engine Build",
        "exec": "bash -c 'cd /home/tehlappy/Desktop/Zelda/ZELDA BLACKENGINE OCT REMASTER/black-engine-zelda-oot && cmake -B build -DCMAKE_BUILD_TYPE=Debug && cmake --build build -j$(nproc)'",
        "icon": "/home/tehlappy/Projects/UnifiedDashboard/public/engine-icon.png",
        "categories": "Development;Building;",
        "comment": "Build BlackSpace Zelda OOT Engine",
        "terminal": True,
        "startupNotify": True,
    },
    {
        "name": "Kairos Dream Scheduler",
        "exec": "bash -c 'cd /home/tehlappy/Projects/Dev Console && python3 kairos_clean.py --session zelda-engine --once'",
        "icon": "/home/tehlappy/Projects/UnifiedDashboard/public/dream-icon.png",
        "categories": "Development;Utility;",
        "comment": "Run Kairos Dream Cycle for Zelda Engine session",
        "terminal": True,
        "startupNotify": False,
    },
    {
        "name": "MSN Cyberpunk Mod Deploy",
        "exec": "bash -c 'cd /home/tehlappy/Projects/Dev Console/vm-ai-gateway/lilith-gateway && python3 -c \"import asyncio; from engine_integration import run_build; asyncio.run(run_build())\"'",
        "icon": "/home/tehlappy/Projects/UnifiedDashboard/public/cyberpunk-icon.png",
        "categories": "Game;Development;",
        "comment": "Deploy Grand Theft Cyberpunk MSN Integration mod",
        "terminal": True,
        "startupNotify": True,
    },
]

def generate_desktop_file(entry: dict) -> str:
    """Generate .desktop file content"""
    lines = [
        "[Desktop Entry]",
        f"Version=1.0",
        f"Type=Application",
        f"Name={entry['name']}",
        f"Comment={entry['comment']}",
        f"Exec={entry['exec']}",
        f"Icon={entry['icon']}",
        f"Terminal={'true' if entry['terminal'] else 'false'}",
        f"Categories={entry['categories']}",
        f"StartupNotify={'true' if entry['startupNotify'] else 'false'}",
        "",
    ]
    return "\n".join(lines)

def install_desktop_files():
    """Install .desktop files to user applications directory"""
    desktop_dir = Path.home() / ".local" / "share" / "applications"
    desktop_dir.mkdir(parents=True, exist_ok=True)
    
    for entry in DESKTOP_ENTRIES:
        # Sanitize filename
        safe_name = entry['name'].lower().replace(' ', '-').replace('.', '')
        desktop_file = desktop_dir / f"{safe_name}.desktop"
        
        content = generate_desktop_file(entry)
        desktop_file.write_text(content)
        desktop_file.chmod(0o755)
        print(f"Created: {desktop_file}")
    
    # Also create on Desktop for quick access
    user_desktop = Path.home() / "Desktop"
    if user_desktop.exists():
        for entry in DESKTOP_ENTRIES:
            safe_name = entry['name'].lower().replace(' ', '-').replace('.', '')
            desktop_file = user_desktop / f"{safe_name}.desktop"
            content = generate_desktop_file(entry)
            desktop_file.write_text(content)
            desktop_file.chmod(0o755)
            print(f"Created Desktop shortcut: {desktop_file}")

if __name__ == "__main__":
    install_desktop_files()
    print("\n✓ All desktop entries created!")
    print("You can now find them in your application menu.")