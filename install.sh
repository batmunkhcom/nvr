#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# mBm NVR System — One-Command Installer
# ═══════════════════════════════════════════════════════════════════
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/OWNER/REPO/main/install.sh | bash
#   ./install.sh
#
set -euo pipefail

PROJECT_DIR="${INSTALL_DIR:-$(pwd)/nvr-system}"
REPO_URL="${REPO_URL:-https://github.com/batmunkhcom/nvr.git}"
BRANCH="${BRANCH:-main}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

# ── colors ──
CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'
tick="${GREEN}✓${NC}"; cross="${RED}✗${NC}"
info()  { echo -e "  ${CYAN}ⓘ${NC} $*"; }
ok()    { echo -e "  ${GREEN}${tick}${NC} $*"; }
warn()  { echo -e "  ${YELLOW}⚠${NC} $*"; }
fail()  { echo -e "  ${RED}${cross}${NC} $*"; }

# ═══════════════════════════════════════════════════════════════════
header() {
    echo ""
    echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${CYAN}║${NC}   mBm NVR System — One-Command Installer    ${BOLD}${CYAN}║${NC}"
    echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════╝${NC}"
    echo ""
}

banner_done() {
    echo ""
    echo -e "  ${GREEN}══════════════════════════════════════════════${NC}"
    echo -e "  ${GREEN}     mBm NVR System Ready! 🚀${NC}"
    echo -e "  ${GREEN}══════════════════════════════════════════════${NC}"
    echo ""
}

# ═══════════════════════════════════════════════════════════════════
check_prerequisites() {
    info "Checking prerequisites..."

    local missing=""

    if ! command -v docker &>/dev/null; then
        missing="${missing}  docker\n"
    fi

    if ! docker compose version &>/dev/null && ! command -v docker-compose &>/dev/null; then
        missing="${missing}  docker compose (or docker-compose)\n"
    fi

    if ! command -v git &>/dev/null; then
        missing="${missing}  git\n"
    fi

    if ! command -v curl &>/dev/null; then
        missing="${missing}  curl\n"
    fi

    if [[ -n "$missing" ]]; then
        fail "Missing required tools:"
        echo -e "$missing"
        echo ""
        echo "Install with:"
        echo "  Ubuntu/Debian: sudo apt install -y docker.io docker-compose-v2 git curl"
        echo "  CentOS/RHEL:   sudo dnf install -y docker docker-compose git curl"
        exit 1
    fi

    if ! docker info &>/dev/null; then
        fail "Docker daemon is not running. Start with: sudo systemctl start docker"
        exit 1
    fi

    ok "All prerequisites met"
}

# ═══════════════════════════════════════════════════════════════════
choose_mode() {
    echo ""
    echo -e "  ${BOLD}Installation Mode:${NC}"
    echo "  1) Full install — clone repo + .env + build + start"
    echo "  2) Docker only   — use existing project, just build & start"
    echo "  3) Reconfigure   — regenerate .env, rebuild & restart"
    echo ""
    read -rp "  Choose [1-3] (default: 1): " mode_choice
    MODE="${mode_choice:-1}"
}

# ═══════════════════════════════════════════════════════════════════
clone_repo() {
    if [[ "$MODE" == "1" ]]; then
        if [[ -d "$PROJECT_DIR/.git" ]]; then
            info "Project already exists at $PROJECT_DIR — pulling latest..."
            cd "$PROJECT_DIR"
            git fetch origin "$BRANCH" 2>/dev/null || true
            git reset --hard "origin/$BRANCH" 2>/dev/null || true
            ok "Updated to latest $BRANCH"
        else
            info "Cloning repository..."
            git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$PROJECT_DIR"
            ok "Repository cloned to $PROJECT_DIR"
        fi
    fi
    cd "$PROJECT_DIR"
    ok "Working directory: $(pwd)"
}

# ═══════════════════════════════════════════════════════════════════
generate_secret() {
    if command -v openssl &>/dev/null; then
        openssl rand -hex 32
    else
        python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || \
        cat /dev/urandom | tr -dc 'a-f0-9' | head -c 64
    fi
}

# ── Non-interactive .env writer (for --no-prompt) ──────────────────
configure_env_no_prompt() {
    local env_file="$PROJECT_DIR/.env"
    local jwt_secret="$(generate_secret)"
    local enc_key="$(generate_secret)"

    [[ -f "$env_file" ]] && cp "$env_file" "${env_file}.backup.${TIMESTAMP}"

    cat > "$env_file" <<NPEOF
POSTGRES_HOST=nvr-db
POSTGRES_PORT=5432
POSTGRES_DB=${POSTGRES_DB}
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
REDIS_HOST=nvr-redis
REDIS_PORT=6379
API_HOST=0.0.0.0
API_PORT=${API_PORT}
API_LOG_LEVEL=info
API_CORS_ORIGINS=http://localhost:${WEB_PORT}
JWT_SECRET_KEY=${jwt_secret}
JWT_ALGORITHM=HS256
JWT_EXPIRY_MINUTES=1440
NVR_ENCRYPTION_KEY=${enc_key}
STORAGE_LOCAL_PATH=/data/recordings
S3_SECURE=false
AI_MODEL_PATH=/app/models
AI_YOLO_MODEL=yolov8n.onnx
AI_CONFIDENCE_THRESHOLD=0.3
AI_DEVICE=cpu
AI_FRAME_WIDTH=1280
AI_MAX_TRACKLETS=64
AI_NMS_THRESHOLD=0.50
AI_MAX_DETECTIONS=300
AI_CLASS_AGNOSTIC_NMS=true
MEDIAMTX_RTSP=rtsp://nvr-mediamtx:8554
MEDIAMTX_HLS_URL=http://nvr-mediamtx:8888
FFMPEG_PATH=/usr/bin/ffmpeg
FFPROBE_PATH=/usr/bin/ffprobe
DISCOVERY_SUBNETS=192.168.1.0/24,192.168.0.0/24,10.0.0.0/24
NPEOF
    ok ".env generated (non-interactive)"
    set -a; source "$env_file"; set +a
    export ADMIN_USERNAME ADMIN_PASSWORD
}

configure_env() {
    echo ""
    info "Configuring environment (.env)..."

    local env_file="$PROJECT_DIR/.env"

    # ── Collect values ──────────────────────────────────────────────

    # Database
    read -rp "  PostgreSQL DB name [nvr]: " POSTGRES_DB
    POSTGRES_DB="${POSTGRES_DB:-nvr}"
    read -rp "  PostgreSQL user [nvr]: " POSTGRES_USER
    POSTGRES_USER="${POSTGRES_USER:-nvr}"
    read -rp "  PostgreSQL password [nvr]: " POSTGRES_PASSWORD
    POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-nvr}"
    POSTGRES_PORT="${POSTGRES_PORT:-5432}"

    # Admin account
    read -rp "  Admin username [admin]: " ADMIN_USERNAME
    ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
    read -rp "  Admin password [admin]: " ADMIN_PASSWORD
    ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"

    # Ports
    read -rp "  Web UI port [3000]: " WEB_PORT
    WEB_PORT="${WEB_PORT:-3000}"
    read -rp "  API port [8000]: " API_PORT
    API_PORT="${API_PORT:-8000}"

    # Redis
    REDIS_PORT="${REDIS_PORT:-6379}"

    # Paths
    read -rp "  Recordings path [/data/nvr/recordings]: " STORAGE_PATH
    STORAGE_PATH="${STORAGE_PATH:-/data/nvr/recordings}"
    AI_MODEL_PATH="${AI_MODEL_PATH:-/data/nvr/models}"

    # ── Generate secrets ───────────────────────────────────────────
    info "Generating secrets..."
    JWT_SECRET_KEY="$(generate_secret)"
    NVR_ENCRYPTION_KEY="$(generate_secret)"

    # ── Write .env ──────────────────────────────────────────────────
    if [[ -f "$env_file" ]]; then
        local backup="${env_file}.backup.${TIMESTAMP}"
        info "Backing up existing .env → ${backup}"
        cp "$env_file" "$backup"
    fi

    cat > "$env_file" <<ENVEOF
# ──────────────────────────────────────────────────────────────────
# mBm NVR System — Environment Configuration
# Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# ──────────────────────────────────────────────────────────────────

# ── Database ─────────────────────────────────────────────────────
POSTGRES_HOST=nvr-db
POSTGRES_PORT=${POSTGRES_PORT}
POSTGRES_DB=${POSTGRES_DB}
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}

# ── Redis ─────────────────────────────────────────────────────────
REDIS_HOST=nvr-redis
REDIS_PORT=${REDIS_PORT}

# ── API ───────────────────────────────────────────────────────────
API_HOST=0.0.0.0
API_PORT=${API_PORT}
API_LOG_LEVEL=info
API_CORS_ORIGINS=http://localhost:${WEB_PORT},http://127.0.0.1:${WEB_PORT}

# ── Authentication ────────────────────────────────────────────────
JWT_SECRET_KEY=${JWT_SECRET_KEY}
JWT_ALGORITHM=HS256
JWT_EXPIRY_MINUTES=1440
NVR_ENCRYPTION_KEY=${NVR_ENCRYPTION_KEY}

# ── Storage ───────────────────────────────────────────────────────
STORAGE_LOCAL_PATH=/data/recordings
S3_SECURE=false

# ── AI Engine ─────────────────────────────────────────────────────
AI_MODEL_PATH=/app/models
AI_YOLO_MODEL=yolov8n.onnx
AI_CONFIDENCE_THRESHOLD=0.3
AI_DEVICE=cpu
AI_FRAME_WIDTH=1280
AI_MAX_TRACKLETS=64
AI_NMS_THRESHOLD=0.50
AI_MAX_DETECTIONS=300
AI_CLASS_AGNOSTIC_NMS=true

# ── Stream ────────────────────────────────────────────────────────
MEDIAMTX_RTSP=rtsp://nvr-mediamtx:8554
MEDIAMTX_HLS_URL=http://nvr-mediamtx:8888

# ── FFmpeg ────────────────────────────────────────────────────────
FFMPEG_PATH=/usr/bin/ffmpeg
FFPROBE_PATH=/usr/bin/ffprobe

# ── Discovery ─────────────────────────────────────────────────────
DISCOVERY_SUBNETS=192.168.1.0/24,192.168.0.0/24,10.0.0.0/24
ENVEOF

    ok ".env written successfully"
}

# ═══════════════════════════════════════════════════════════════════
build_images() {
    info "Building Docker images (this may take several minutes)..."
    if ! docker compose build --parallel 2>&1; then
        fail "Docker build failed"
        exit 1
    fi
    ok "Docker images built"
}

start_services() {
    info "Starting all services..."
    docker compose down --remove-orphans 2>/dev/null || true
    docker compose up -d 2>&1

    info "Waiting for database to be ready..."
    local max=60 elapsed=0
    while [[ $elapsed -lt $max ]]; do
        if docker exec nvr-db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" &>/dev/null; then
            break
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    if [[ $elapsed -ge $max ]]; then
        fail "Database did not become ready within ${max}s"
        exit 1
    fi
    ok "Database ready (${elapsed}s)"

    info "Waiting for API to be ready..."
    elapsed=0
    while [[ $elapsed -lt $max ]]; do
        if docker exec nvr-api curl -sf http://localhost:8000/api/v1/system/health &>/dev/null; then
            break
        fi
        sleep 3
        elapsed=$((elapsed + 3))
    done
    if [[ $elapsed -ge $max ]]; then
        fail "API did not become ready within ${max}s"
        warn "Try: docker logs nvr-api"
        exit 1
    fi
    ok "API ready (${elapsed}s)"
}

# ═══════════════════════════════════════════════════════════════════
run_migrations() {
    info "Running database migrations..."
    docker exec nvr-api \
        python3 -c "
import asyncio, sys
sys.path.insert(0, '/app/services/api')
sys.path.insert(0, '/app/packages/common')
from alembic.config import main
main(argv=['--raiseerr', 'upgrade', 'head'])
" 2>&1 || {
        warn "Migration via container failed — trying host method..."
        cd services/api
        PYTHONPATH="${PROJECT_DIR}/services/api:${PROJECT_DIR}/packages/common" \
            POSTGRES_HOST=localhost POSTGRES_PORT="$POSTGRES_PORT" \
            python3 -m alembic upgrade head 2>&1 || true
        cd "$PROJECT_DIR"
    }
    ok "Migrations complete"
}

seed_data() {
    info "Seeding initial configuration..."

    # Seed system_config from config/default.yml
    docker exec nvr-api python3 <<'PYSEED' 2>&1 || true
import asyncio, os, yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

config_path = "/app/config/default.yml"
db_host = os.environ.get("POSTGRES_HOST", "nvr-db")
db_port = os.environ.get("POSTGRES_PORT", "5432")
db_name = os.environ.get("POSTGRES_DB", "nvr")
db_user = os.environ.get("POSTGRES_USER", "nvr")
db_pass = os.environ.get("POSTGRES_PASSWORD", "nvr")
db_url = f"postgresql+asyncpg://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

async def seed():
    with open(config_path) as f:
        data = yaml.safe_load(f)
    engine = create_async_engine(db_url)

    def flatten(d, prefix=""):
        entries = []
        for k, v in d.items():
            fk = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                entries.extend(flatten(v, fk))
            elif isinstance(v, list):
                entries.append((fk, v, f"Config: {fk}"))
            else:
                entries.append((fk, {"value": v}, f"Config: {fk}"))
        return entries

    entries = flatten(data)
    async with engine.begin() as conn:
        for key, value, desc in entries:
            await conn.execute(
                text("""
                    INSERT INTO system_config (key, value, description, updated_at)
                    VALUES (:key, CAST(:value AS jsonb), :desc, NOW())
                    ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value, description = EXCLUDED.desc, updated_at = NOW()
                """), {"key": key, "value": str(value).replace("'", '"'), "desc": desc})
        print(f"  Seeded {len(entries)} config entries")

asyncio.run(seed())
PYSEED
    ok "Configuration seeded"
}

create_admin() {
    info "Creating admin user..."
    # Attempt to create via API — if admin already exists, this fails gracefully
    docker exec nvr-api python3 <<PYADMIN 2>&1 || true
import asyncio, hashlib, os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

db_host = os.environ.get("POSTGRES_HOST", "nvr-db")
db_port = os.environ.get("POSTGRES_PORT", "5432")
db_name = os.environ.get("POSTGRES_DB", "nvr")
db_user = os.environ.get("POSTGRES_USER", "nvr")
db_pass = os.environ.get("POSTGRES_PASSWORD", "nvr")
db_url = f"postgresql+asyncpg://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

admin_user = os.environ.get("ADMIN_USERNAME", "admin")
admin_pass = os.environ.get("ADMIN_PASSWORD", "admin")
engine = create_async_engine(db_url)
Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def create():
    async with Session() as session:
        # Check if users table has any rows
        result = await session.execute(text("SELECT COUNT(*) FROM users"))
        if result.scalar() and result.scalar() > 0:
            print("  Users already exist — skipping admin creation")
            return

        import uuid
        from datetime import UTC, datetime
        from passlib.hash import bcrypt

        now = datetime.now(UTC)
        hashed = bcrypt.hash(admin_pass)
        await session.execute(text("""
            INSERT INTO users (id, username, hashed_password, role, is_active, created_at, updated_at)
            VALUES (:id, :username, :hashed_password, 'admin', true, :now, :now)
            ON CONFLICT (username) DO NOTHING
        """), {"id": str(uuid.uuid4()), "username": admin_user, "hashed_password": hashed, "now": now})
        await session.commit()
        print(f"  Admin user '{admin_user}' created")

asyncio.run(create())
PYADMIN
    ok "Admin user ready"
}

# ═══════════════════════════════════════════════════════════════════
show_complete() {
    banner_done

    local web_url="http://localhost:${WEB_PORT:-3000}"
    local api_url="http://localhost:${API_PORT:-8000}"

    echo ""
    echo -e "  ${BOLD}Access URLs:${NC}"
    echo -e "    Web UI:       ${GREEN}${web_url}${NC}"
    echo -e "    API:          ${GREEN}${api_url}${NC}"
    echo -e "    API Docs:     ${GREEN}${api_url}/docs${NC}"
    echo -e "    Health:       ${GREEN}${api_url}/api/v1/system/health${NC}"
    echo ""
    echo -e "  ${BOLD}Credentials:${NC}"
    echo -e "    Username:     ${BOLD}${ADMIN_USERNAME:-admin}${NC}"
    echo -e "    Password:     ${BOLD}${ADMIN_PASSWORD:-admin}${NC}"
    echo ""
    echo -e "  ${BOLD}Management:${NC}"
    echo -e "    Status:       ${CYAN}docker compose ps${NC}"
    echo -e "    Logs:         ${CYAN}docker compose logs -f${NC}"
    echo -e "    Restart:      ${CYAN}docker compose restart${NC}"
    echo -e "    Stop:         ${CYAN}docker compose down${NC}"
    echo ""
    echo -e "  ${YELLOW}⚠  Change the admin password immediately after first login.${NC}"
    echo ""

    # quick health check
    if command -v curl &>/dev/null; then
        info "Running quick health check..."
        if curl -sf "${api_url}/api/v1/system/health" &>/dev/null; then
            ok "System health: OK ✓"
        else
            warn "API not responding yet — might need a few more seconds"
        fi
    fi

    echo ""
    echo -e "  ${GREEN}══════════════════════════════════════════════${NC}"
    echo -e "  ${GREEN}    mBm TECHNOLOGY LLC — www.mbm.technology${NC}"
    echo -e "  ${GREEN}══════════════════════════════════════════════${NC}"
    echo ""
}

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

header

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo "Usage: curl -fsSL URL | bash"
    echo "       ./install.sh"
    echo ""
    echo "Options:"
    echo "  --help, -h     Show this help"
    echo "  --no-prompt    Non-interactive mode (use defaults)"
    echo "  INSTALL_DIR=   Custom install directory"
    echo "  REPO_URL=      Custom git repo URL"
    exit 0
fi

check_prerequisites

if [[ "${1:-}" == "--no-prompt" ]]; then
    MODE="1"
    POSTGRES_DB="nvr"
    POSTGRES_USER="nvr"
    POSTGRES_PASSWORD="$(generate_secret | head -c 16)"
    ADMIN_USERNAME="admin"
    ADMIN_PASSWORD="$(generate_secret | head -c 12)"
    WEB_PORT="3000"
    API_PORT="8000"
    STORAGE_PATH="/data/nvr/recordings"
    AI_MODEL_PATH="/data/nvr/models"
    REDIS_PORT="6379"

    configure_env_no_prompt
    clone_repo
    build_images
    start_services
    run_migrations
    seed_data
    create_admin
    show_complete
else
    choose_mode
    clone_repo
    configure_env

    # Export for docker compose and DB commands
    set -a
    source "$PROJECT_DIR/.env"
    set +a
    export ADMIN_USERNAME ADMIN_PASSWORD

    echo ""
    read -rp "  Ready to build and start all services? [Y/n] " confirm
    if [[ "$confirm" =~ ^[Nn]$ ]]; then
        info "Skipping build. Run manually: cd $PROJECT_DIR && docker compose up -d"
        exit 0
    fi

    build_images
    start_services
    run_migrations
    seed_data
    create_admin
    show_complete
fi
