#!/bin/bash
# SeaweedFS NFS HA Watchdog — cycles through NFS servers on mount failure
# Called by systemd timer every 60s

SERVERS=(10.10.95.102 10.10.95.104 10.10.95.106 10.10.95.107)
MOUNT_POINT=/mnt/seaweedfs
NFS_PATH=/
NFS_OPTS="nfsvers=4,hard,timeo=300,retrans=3,bg"
CURRENT_INDEX_FILE=/var/run/nvr-nfs-index
HEALTH_FILE=${MOUNT_POINT}/.nfs_health
LOG_TAG="nvr-nfs-ha"

CURRENT=0
[ -f "$CURRENT_INDEX_FILE" ] && CURRENT=$(cat "$CURRENT_INDEX_FILE")

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | systemd-cat -t "$LOG_TAG" -p info 2>/dev/null
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

mount_nfs() {
    local idx=$1
    local server=${SERVERS[$idx]}
    mount -t nfs -o "$NFS_OPTS" "${server}:${NFS_PATH}" "$MOUNT_POINT" 2>/dev/null
    return $?
}

check_health() {
    timeout 5 touch "$HEALTH_FILE" 2>/dev/null && rm -f "$HEALTH_FILE"
    return $?
}

# Check current mount
if [ ! -f "$HEALTH_FILE" ] || ! check_health; then
    if mountpoint -q "$MOUNT_POINT" 2>/dev/null; then
        log "NFS stale or unreachable, umounting..."
        umount -f -l "$MOUNT_POINT" 2>/dev/null
        sleep 2
    fi

    # Try all servers round-robin starting from next server
    for ((i=0; i<${#SERVERS[@]}; i++)); do
        NEXT=$(( (CURRENT + i + 1) % ${#SERVERS[@]} ))
        log "Trying NFS mount from ${SERVERS[$NEXT]}..."
        if mount_nfs "$NEXT"; then
            echo "$NEXT" > "$CURRENT_INDEX_FILE"
            log "Mounted successfully from ${SERVERS[$NEXT]}"
            exit 0
        fi
        sleep 2
    done

    log "CRITICAL: ALL NFS servers failed after $((${#SERVERS[@]})) attempts!"
    exit 1
fi
