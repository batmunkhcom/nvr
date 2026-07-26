#!/bin/bash
# Install SeaweedFS NFS HA Watchdog as systemd timer (runs every 60s)
# Usage: sudo bash scripts/setup-nfs-ha.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WATCHDOG="$SCRIPT_DIR/nfs-ha-watchdog.sh"

if [ ! -f "$WATCHDOG" ]; then
    echo "ERROR: nfs-ha-watchdog.sh not found in $SCRIPT_DIR"
    exit 1
fi

chmod +x "$WATCHDOG"

# Mount point
MOUNT_POINT=/mnt/seaweedfs
mkdir -p "$MOUNT_POINT"

# Initial mount
echo "Mounting NFS from 10.10.95.102..."
mount -t nfs -o nfsvers=4,hard,timeo=300,retrans=3,bg 10.10.95.102:/ "$MOUNT_POINT" 2>/dev/null || \
    echo "Initial mount failed — watchdog will retry. Continue installing..."

# systemd service
cat > /etc/systemd/system/nvr-nfs-ha.service << 'SVC'
[Unit]
Description=NVR SeaweedFS NFS HA Watchdog
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=WATCHDOG_PATH
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVC

# Replace path placeholder
sed -i "s|WATCHDOG_PATH|$WATCHDOG|" /etc/systemd/system/nvr-nfs-ha.service

# systemd timer
cat > /etc/systemd/system/nvr-nfs-ha.timer << 'TMR'
[Unit]
Description=NVR SeaweedFS NFS HA Watchdog Timer
Requires=nvr-nfs-ha.service

[Timer]
OnBootSec=30s
OnUnitActiveSec=60s
AccuracySec=5s

[Install]
WantedBy=timers.target
TMR

systemctl daemon-reload
systemctl enable nvr-nfs-ha.timer
systemctl start nvr-nfs-ha.timer

echo "NFS HA Watchdog installed:"
echo "  Service: systemctl status nvr-nfs-ha"
echo "  Timer:   systemctl status nvr-nfs-ha.timer"
echo "  Logs:    journalctl -u nvr-nfs-ha -f"
