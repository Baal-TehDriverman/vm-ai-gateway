#!/bin/bash
# 🜏 VM Helper — Create, manage, and connect to VMs
GATEWAY="$(cd "$(dirname "$0")" && pwd)"

case "${1:-help}" in
    list)
        echo "── Virtual Machines ──"
        virsh list --all 2>/dev/null || echo "(libvirt not running)"
        ;;
    start)
        if [ -z "$2" ]; then echo "Usage: $0 start <vm-name>"; exit 1; fi
        virsh start "$2" && echo "Started $2"
        ;;
    shutdown)
        if [ -z "$2" ]; then echo "Usage: $0 shutdown <vm-name>"; exit 1; fi
        virsh shutdown "$2" && echo "Shutdown signal sent to $2"
        ;;
    console)
        if [ -z "$2" ]; then echo "Usage: $0 console <vm-name>"; exit 1; fi
        virt-viewer -c qemu:///system "$2" &
        echo "Opening console for $2..."
        ;;
    create)
        virt-manager &
        echo "Opening virt-manager for VM creation..."
        ;;
    status)
        echo "── Libvirt Status ──"
        systemctl --user status libvirtd 2>/dev/null || systemctl status libvirtd 2>/dev/null || echo "libvirtd status unknown"
        virsh list --all 2>/dev/null
        ;;
    *)
        echo "🜏 VM Helper — Virtual Machine Management"
        echo "Commands: list, start <vm>, shutdown <vm>, console <vm>, create, status"
        ;;
esac
