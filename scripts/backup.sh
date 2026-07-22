#!/usr/bin/env bash
# nvr-backup — full NVR system configuration backup.
#
# Backs up: PostgreSQL database, config files, docker-compose, .env
# Optional encryption: --encrypt (prompts) or NVR_BACKUP_PASSWORD env var.
#
# Usage:
#   ./scripts/backup.sh                     # plain .tar.gz into ./backups
#   ./scripts/backup.sh --encrypt           # encrypted .tar.gz.enc
#   NVR_BACKUP_DIR=/mnt/nas ./scripts/backup.sh
#   NVR_BACKUP_KEEP=30 ./scripts/backup.sh  # keep 30 backups (default 10)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${NVR_BACKUP_DIR:-$ROOT/backups}"
KEEP="${NVR_BACKUP_KEEP:-10}"
ENCRYPT=0
[[ "${1:-}" == "--encrypt" ]] && ENCRYPT=1

TS="$(date +%Y%m%d-%H%M%S)"
NAME="nvr-backup-$TS"
WORK="$(mktemp -d)/$NAME"
mkdir -p "$WORK" "$BACKUP_DIR"

log() { echo "[backup] $*"; }
die() { echo "[backup] ERROR: $*" >&2; exit 1; }

# ── 1. Database dump ────────────────────────────────────────────────────────
log "dumping database (pg_dump from nvr-db container)..."
docker exec nvr-db pg_dump -U nvr_user -d nvr --no-owner --no-privileges \
  | gzip -9 > "$WORK/db.sql.gz" || die "pg_dump failed"
DB_SIZE=$(stat -c%s "$WORK/db.sql.gz")
[[ "$DB_SIZE" -lt 100 ]] && die "db dump suspiciously small ($DB_SIZE bytes)"
log "  db.sql.gz: $((DB_SIZE / 1024)) KB"

# ── 2. Config files ─────────────────────────────────────────────────────────
log "collecting config files..."
mkdir -p "$WORK/config"
cp -r "$ROOT/config/." "$WORK/config/"
cp "$ROOT/docker-compose.yml" "$WORK/" 2>/dev/null || true
cp "$ROOT/.env" "$WORK/env.plain" 2>/dev/null || log "  (no .env file — skipping)"

# ── 3. Manifest ─────────────────────────────────────────────────────────────
GIT_SHA="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
cat > "$WORK/manifest.json" <<EOF
{
  "name": "$NAME",
  "created_at": "$(date -Iseconds)",
  "git_sha": "$GIT_SHA",
  "hostname": "$(hostname)",
  "contents": ["db.sql.gz", "config/", "docker-compose.yml", "env.plain"],
  "encrypted": $ENCRYPT
}
EOF

# ── 4. Archive ──────────────────────────────────────────────────────────────
ARCHIVE="$BACKUP_DIR/$NAME.tar.gz"
tar -czf "$ARCHIVE" -C "$(dirname "$WORK")" "$NAME"
rm -rf "$(dirname "$WORK")"

# ── 5. Optional encryption ──────────────────────────────────────────────────
if [[ "$ENCRYPT" -eq 1 ]]; then
  PASS="${NVR_BACKUP_PASSWORD:-}"
  if [[ -z "$PASS" ]]; then
    read -rsp "Backup encryption password: " PASS; echo
    read -rsp "Confirm password: " PASS2; echo
    [[ "$PASS" != "$PASS2" ]] && die "passwords do not match"
  fi
  openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
    -in "$ARCHIVE" -out "$ARCHIVE.enc" -pass "pass:$PASS"
  rm -f "$ARCHIVE"
  ARCHIVE="$ARCHIVE.enc"
  log "encrypted with AES-256-CBC (PBKDF2, 200k iterations)"
fi

sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"
log "created: $ARCHIVE ($(( $(stat -c%s "$ARCHIVE") / 1024 / 1024 )) MB)"

# ── 6. Retention — keep last N ──────────────────────────────────────────────
ls -1t "$BACKUP_DIR"/nvr-backup-*.tar.gz* 2>/dev/null \
  | grep -v '\.sha256$' | tail -n +"$((KEEP + 1))" | while read -r old; do
    log "pruning old backup: $(basename "$old")"
    rm -f "$old" "$old.sha256"
done

log "done. Restore with: ./scripts/restore.sh $ARCHIVE"
