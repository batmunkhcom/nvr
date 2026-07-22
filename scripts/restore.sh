#!/usr/bin/env bash
# nvr-restore — restore an NVR backup created by scripts/backup.sh
#
# Usage:
#   ./scripts/restore.sh backups/nvr-backup-20260723-120000.tar.gz
#   ./scripts/restore.sh backups/nvr-backup-20260723-120000.tar.gz.enc
#
# WARNING: this OVERWRITES the current database and config files.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCHIVE="${1:-}"

log() { echo "[restore] $*"; }
die() { echo "[restore] ERROR: $*" >&2; exit 1; }

[[ -z "$ARCHIVE" ]] && die "usage: $0 <backup-archive>"
[[ -f "$ARCHIVE" ]] || die "file not found: $ARCHIVE"

# ── 0. Verify checksum if present ───────────────────────────────────────────
if [[ -f "$ARCHIVE.sha256" ]]; then
  log "verifying checksum..."
  (cd "$(dirname "$ARCHIVE")" && sha256sum -c "$(basename "$ARCHIVE.sha256")") \
    || die "checksum mismatch — archive is corrupt"
fi

# ── 1. Decrypt if needed ────────────────────────────────────────────────────
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
TARBALL="$ARCHIVE"
if [[ "$ARCHIVE" == *.enc ]]; then
  PASS="${NVR_BACKUP_PASSWORD:-}"
  if [[ -z "$PASS" ]]; then
    read -rsp "Backup decryption password: " PASS; echo
  fi
  log "decrypting..."
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
    -in "$ARCHIVE" -out "$WORK/backup.tar.gz" -pass "pass:$PASS" \
    || die "decryption failed (wrong password?)"
  TARBALL="$WORK/backup.tar.gz"
fi

tar -xzf "$TARBALL" -C "$WORK"
DIR="$(find "$WORK" -maxdepth 1 -mindepth 1 -type d -name 'nvr-backup-*' | head -1)"
[[ -d "$DIR" ]] || die "invalid archive structure"

[[ -f "$DIR/manifest.json" ]] && cat "$DIR/manifest.json" && echo
read -rp "This will OVERWRITE the current DB and config. Continue? [y/N] " yn
[[ "${yn,,}" == "y" ]] || die "aborted"

# ── 2. Stop writers, restore DB ─────────────────────────────────────────────
log "stopping api..."
docker stop nvr-api >/dev/null 2>&1 || true

log "restoring database..."
docker exec -i nvr-db psql -U nvr_user -d nvr -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='nvr' AND pid <> pg_backend_pid();" \
  >/dev/null 2>&1 || true
gunzip -c "$DIR/db.sql.gz" | docker exec -i nvr-db psql -U nvr_user -d nvr -v ON_ERROR_STOP=1 -q \
  || die "database restore failed"
log "  database restored"

# ── 3. Restore config files ─────────────────────────────────────────────────
log "restoring config files..."
cp -r "$DIR/config/." "$ROOT/config/"
[[ -f "$DIR/docker-compose.yml" ]] && cp "$DIR/docker-compose.yml" "$ROOT/"
[[ -f "$DIR/env.plain" ]] && cp "$DIR/env.plain" "$ROOT/.env" && chmod 600 "$ROOT/.env"

# ── 4. Restart ──────────────────────────────────────────────────────────────
log "starting api..."
docker start nvr-api >/dev/null 2>&1 || docker compose -f "$ROOT/docker-compose.yml" up -d nvr-api
log "done. Verify: curl http://localhost:8000/api/v1/system/health"
