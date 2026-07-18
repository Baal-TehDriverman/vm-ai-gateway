#!/usr/bin/env python3
"""Scan system for installed GUI applications and write apps.json"""
import json, os, glob
from pathlib import Path

def parse_desktop(fp):
    """Extract name, exec, icon, categories from a .desktop file"""
    name = ""; exec_cmd = ""; icon = ""; categories = ""; no_display = False; terminal = False
    try:
        content = fp.read_text(encoding="utf-8", errors="replace")
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("Name=") and not name:
                name = line[5:].strip()
            elif line.startswith("Exec=") and not exec_cmd:
                exec_cmd = line[5:].strip()
            elif line.startswith("Icon=") and not icon:
                icon = line[5:].strip()
            elif line.startswith("Categories=") and not categories:
                categories = line[11:].strip()
            elif line.startswith("NoDisplay="):
                no_display = line[10:].strip() == "true"
            elif line.startswith("Terminal="):
                terminal = line[9:].strip() == "true"
    except: pass
    return name, exec_cmd, icon, categories, no_display, terminal

def resolve_icon(icon_name, size=48):
    """Try to find icon file path"""
    if not icon_name or icon_name == "":
        return None
    # Check common locations
    for base in ["/usr/share/icons/hicolor", "/usr/share/icons/breeze", "/usr/share/pixmaps"]:
        for ext in [".svg", ".png", ".xpm"]:
            p = Path(f"{base}/{size}x{size}/apps/{icon_name}{ext}")
            if p.exists(): return str(p)
            p = Path(f"{base}/scalable/apps/{icon_name}.svg")
            if p.exists(): return str(p)
        p = Path(f"/usr/share/pixmaps/{icon_name}.png")
        if p.exists(): return str(p)
        p = Path(f"/usr/share/pixmaps/{icon_name}.xpm")
        if p.exists(): return str(p)
    return None

apps = []
seen = set()

# Scan system applications
search_dirs = [
    "/usr/share/applications",
    "/usr/local/share/applications",
    os.path.expanduser("~/.local/share/applications"),
    "/var/lib/snapd/desktop/applications",
    "/var/lib/flatpak/exports/share/applications",
]

for d in search_dirs:
    if not os.path.isdir(d): continue
    for f in sorted(glob.glob(os.path.join(d, "*.desktop"))):
        fp = Path(f)
        name, exec_cmd, icon, categories, no_display, terminal = parse_desktop(fp)
        if not name or no_display: continue
        if name in seen: continue
        seen.add(name)
        
        # Clean exec command
        exec_clean = exec_cmd
        for token in ["%U", "%u", "%F", "%f", "%i", "%c", "%k"]:
            exec_clean = exec_clean.replace(token, "").strip()
        
        apps.append({
            "name": name,
            "exec": exec_clean,
            "icon": resolve_icon(icon),
            "icon_name": icon,
            "categories": categories.split(";") if categories else [],
            "terminal": terminal,
            "desktop_file": f,
        })

# Sort alphabetically
apps.sort(key=lambda a: a["name"].lower())

output = {
    "apps": apps,
    "count": len(apps),
    "generated": __import__("datetime").datetime.now().isoformat(),
}

GATEWAY = os.path.dirname(os.path.abspath(__file__))
Path(os.path.join(GATEWAY, "apps.json")).write_text(json.dumps(output, indent=2))
print(f"Scanned {len(apps)} applications → apps.json")
