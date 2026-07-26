#!/bin/bash
# SeaweedFS FUSE Mount — systemd service installer
#
# SeaweedFS FUSE client connects to all 4 filers in a single mount:
#   weed mount -filer=10.10.95.102:8888,10.10.95.104:8888,...
#
# The FUSE client handles HA internally — if one filer fails, it
# automatically switches to the next. No external watchdog needed.
# This script only ensures the mount process restarts if it crashes.
#
# Usage: sudo bash scripts/mount-seaweedfs.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MOUNT_POINT="${SEAWEEDFS_MOUNT_PATH:-/mnt/seaweedfs}"

# Load env file if present (for SEAWEEDFS_FILER_PEERS)
ENV_FILE="$SCRIPT_DIR/../.env"
if [ -f "$ENV_FILE" ]; then
    set -a; source "$ENV_FILE"; set +a
fi
FILER_PEERS="${SEAWEEDFS_FILER_PEERS:-}"

if [ -z "$FILER_PEERS" ]; then
    echo "ERROR: SEAWEEDFS_FILER_PEERS not set in .env"
    echo "Example: SEAWEEDFS_FILER_PEERS=10.10.95.102:8888,10.10.95.104:8888,..."
    exit 1
fi

mkdir -p "$MOUNT_POINT"

# Check weed binary
if ! command -v weed &>/dev/null; then
    echo "ERROR: 'weed' binary not found. Install seaweedfs client first:"
    echo "  wget https://github.com/seaweedfs/seaweedfs/releases/latest/download/linux_amd64.tar.gz"
    echo "  tar xzf linux_amd64.tar.gz -C /usr/local/bin/ weed"
    exit 1
fi

# Stop existing mount if any
if mountpoint -q "$MOUNT_POINT" 2>/dev/null; then
    echo "Unmounting existing $MOUNT_POINT..."
    fusermount -u "$MOUNT_POINT" 2>/dev/null || umount -l "$MOUNT_POINT" 2>/dev/null
    sleep 1
fi

# Initial mount
echo "Mounting SeaweedFS FUSE at $MOUNT_POINT..."
weed mount -filer="$FILER_PEERS" -dir="$MOUNT_POINT" \
    -filer.path=/ \
    -concurrentWriters=16 \
    -cacheCapacityMB=512 \
    &

sleep 3
if mountpoint -q "$MOUNT_POINT" 2>/dev/null; then
    echo "Mounted: $(mount | grep "$MOUNT_POINT")"
else
    echo "WARNING: Initial mount check failed — systemd will retry."
fi

# systemd service: restart weed mount if process crashes
cat > /etc/systemd/system/seaweedfs-mount.service << SVC
[Unit]
Description=SeaweedFS FUSE Mount
After=network-online.target
Wants=network-online.target

[Service]
Type=forking
ExecStart=/usr/local/bin/weed mount -filer=${FILER_PEERS} -dir=${MOUNT_POINT} -filer.path=/ -concurrentWriters=16 -cacheCapacityMB=512
ExecStop=/bin/bash -c 'fusermount -u ${MOUNT_POINT} 2>/dev/null || umount -l ${MOUNT_POINT}'
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVC

systemctl daemon-reload
systemctl enable seaweedfs-mount.service
systemctl start seaweedfs-mount.service 2>/dev/null || echo "Service start failed — check: systemctl status seaweedfs-mount"

echo ""
echo "SeaweedFS FUSE Mount installed:"
echo "  Service: systemctl status seaweedfs-mount"
echo "  Logs:    journalctl -u seaweedfs-mount -f"
echo "  Mount:   df -h $MOUNT_POINT"
echo ""
echo "Next: Add mount point to docker-compose .env:"
echo "  SEAWEEDFS_MOUNT_PATH=$MOUNT_POINT"
echo ""
echo "Admin panel → Storage → Backends → Create:"
echo "  name: SeaweedFS Cluster"
echo "  backend_type: nfs"
echo "  mount_point: $MOUNT_POINT"
