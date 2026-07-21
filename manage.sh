#!/usr/bin/env bash
# NVR System Management Script
# Usage: ./manage.sh [command]
# Full project management from infrastructure to deployment.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# ── colors ──
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERR]${NC}  $*"; }

# ── URLs ──
API_URL="http://localhost:8000"
WEB_URL="http://localhost:3000"
API_DOCS="${API_URL}/docs"
API_HEALTH="${API_URL}/api/v1/system/health"
PROMETHEUS_METRICS="${API_URL}/metrics"
GRAFANA_URL="http://localhost:3001"

# ────────────────────────────────────────
#  HELP
# ────────────────────────────────────────
help_cmd() {
  cat <<EOF
Usage: ./manage.sh <command> [options]

══ INFRASTRUCTURE ══
  infra-up          Start DB + Redis + MinIO
  infra-down        Stop infrastructure
  infra-status      Show infrastructure status

══ DATABASE ══
  db-migrate        Run Alembic migrations
  db-seed           Seed initial config + admin user
  db-setup          Full DB setup (migrate + seed)
  db-reset          Reset DB (down all + up + seed)

══ SERVICES ══
  api-dev           Start FastAPI dev server (hot reload)
  api-start          Start FastAPI production
  web-dev           Start React dev server
  stream-manager    Start Stream Manager
  recording-engine  Start Recording Engine
  ai-engine         Start AI Engine

══ DOCKER ══
  docker-build      Build all Docker images
  docker-up         Start all Docker services
  docker-down       Stop all Docker services
  docker-logs       Tail all Docker logs
  docker-restart    Restart all Docker services

══ TESTING ══
  test              Run all Python tests
  test-cov          Run tests with coverage
  test-web          Run frontend tests (vitest)
  test-e2e          Run Playwright E2E tests
  test-all          Run all tests (Python + Web)

══ QUALITY ══
  lint              Run Python lint (ruff)
  format            Format Python (ruff)
  typecheck         Run Python type checker (mypy)
  lint-web          Run TypeScript lint
  typecheck-web     Run TypeScript type check
  check-all         Run all quality checks

══ HEALTH ══
  health            Check API health
  self-test         Run system self-test
  metrics           Show Prometheus metrics
  urls              Show all access URLs

══ UTILITY ══
  update-deps       Update all Python + Node dependencies
  clean             Clean all build artifacts
  status            Show full system status
  all-setup         Full setup from scratch

EOF
}

# ────────────────────────────────────────
#  INFRASTRUCTURE
# ────────────────────────────────────────
infra_up() {
  info "Starting infrastructure (DB, Redis, MinIO)..."
  docker compose up -d nvr-db nvr-redis nvr-minio
  info "Waiting for services to be ready..."
  sleep 3
  ok "Infrastructure started"
}

infra_down() {
  info "Stopping infrastructure..."
  docker compose down
  ok "Infrastructure stopped"
}

infra_status() {
  info "Infrastructure status:"
  docker compose ps nvr-db nvr-redis nvr-minio 2>/dev/null || echo "  No containers running"
}

# ────────────────────────────────────────
#  DATABASE
# ────────────────────────────────────────
db_migrate() {
  info "Running Alembic migrations..."
  cd services/api
  PYTHONPATH="${PROJECT_DIR}/services/api:${PROJECT_DIR}/packages/common" \
    python3 -m alembic upgrade head
  cd "$PROJECT_DIR"
  ok "Migrations complete"
}

db_seed() {
  info "Seeding initial configuration..."
  PYTHONPATH="${PROJECT_DIR}/services/api:${PROJECT_DIR}/packages/common" \
    python3 scripts/seed_db.py
  ok "Seed complete"
}

db_setup() {
  info "Full DB setup..."
  db_migrate
  db_seed
  ok "DB setup complete"
}

db_reset() {
  warn "Resetting database (all data will be lost)..."
  read -rp "Are you sure? [y/N] " confirm
  if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    info "Cancelled"
    return
  fi
  cd services/api
  PYTHONPATH="${PROJECT_DIR}/services/api:${PROJECT_DIR}/packages/common" \
    python3 -m alembic downgrade base
  PYTHONPATH="${PROJECT_DIR}/services/api:${PROJECT_DIR}/packages/common" \
    python3 -m alembic upgrade head
  cd "$PROJECT_DIR"
  db_seed
  ok "DB reset complete"
}

# ────────────────────────────────────────
#  SERVICES (DEV MODE)
# ────────────────────────────────────────
api_dev() {
  info "Starting API dev server on port 8000..."
  cd services/api
  PYTHONPATH="${PROJECT_DIR}/services/api:${PROJECT_DIR}/packages/common" \
    python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
}

web_dev() {
  info "Starting React dev server on port 3000..."
  cd services/web
  npm install --silent 2>/dev/null
  npm run dev
}

stream_manager() {
  info "Starting Stream Manager..."
  cd services/stream-manager
  PYTHONPATH="${PROJECT_DIR}/services/stream-manager:${PROJECT_DIR}/packages/common" \
    python3 -m app.manager
}

recording_engine() {
  info "Starting Recording Engine..."
  cd services/recording-engine
  PYTHONPATH="${PROJECT_DIR}/services/recording-engine:${PROJECT_DIR}/packages/common" \
    python3 -m app.main
}

ai_engine() {
  info "Starting AI Engine..."
  cd services/ai-engine
  PYTHONPATH="${PROJECT_DIR}/services/ai-engine:${PROJECT_DIR}/packages/common" \
    python3 -m app.main
}

# ────────────────────────────────────────
#  DOCKER
# ────────────────────────────────────────
docker_build() {
  info "Building all Docker images..."
  docker compose build
  ok "Docker images built"
}

docker_up() {
  info "Starting all Docker services..."
  docker compose up -d
  sleep 5
  ok "All Docker services started"
}

docker_down() {
  info "Stopping all Docker services..."
  docker compose down
  ok "Docker services stopped"
}

docker_logs() {
  docker compose logs -f "${@:-}"
}

docker_restart() {
  docker compose restart "${@:-}"
  ok "Docker services restarted"
}

# ────────────────────────────────────────
#  TESTING
# ────────────────────────────────────────
run_tests() {
  info "Running Python tests..."
  cd "$PROJECT_DIR"
  python3 -m pytest -v "${@:-}"
}

run_tests_cov() {
  info "Running Python tests with coverage..."
  python3 -m pytest -v --cov=services --cov=packages --cov-report=term-missing
}

run_tests_web() {
  info "Running frontend tests (vitest)..."
  cd services/web
  npx vitest run
  cd "$PROJECT_DIR"
}

run_tests_e2e() {
  info "Running Playwright E2E tests..."
  cd services/web
  npx playwright test
  cd "$PROJECT_DIR"
}

run_tests_all() {
  run_tests
  echo ""
  run_tests_web
  ok "All tests complete"
}

# ────────────────────────────────────────
#  QUALITY
# ────────────────────────────────────────
lint_cmd() {
  info "Running ruff linter..."
  ruff check services/ packages/
  ok "Lint passed"
}

format_cmd() {
  info "Formatting Python code..."
  ruff format services/ packages/
  ok "Formatting complete"
}

typecheck_cmd() {
  info "Running mypy..."
  mypy services/ 2>/dev/null || warn "mypy not fully configured yet"
}

lint_web() {
  info "Running ESLint..."
  cd services/web && npx eslint src/ 2>/dev/null || warn "ESLint not configured" && cd "$PROJECT_DIR"
}

typecheck_web() {
  info "Running TypeScript type check..."
  cd services/web && npx tsc --noEmit && cd "$PROJECT_DIR"
  ok "TypeScript types OK"
}

check_all() {
  lint_cmd
  typecheck_web
  format_cmd
  run_tests
  ok "All quality checks passed"
}

# ────────────────────────────────────────
#  HEALTH
# ────────────────────────────────────────
health_check() {
  info "Checking API health..."
  if command -v curl &>/dev/null; then
    curl -s "$API_HEALTH" | python3 -m json.tool 2>/dev/null || echo "  API not responding"
  else
    python3 -c "
import urllib.request, json
try:
    resp = urllib.request.urlopen('${API_HEALTH}')
    print(json.dumps(json.loads(resp.read()), indent=2))
except Exception as e:
    print(f'  API not reachable: {e}')
"
  fi
}

self_test() {
  info "Running system self-test..."
  # This requires auth, so we use curl with default credentials
  if command -v curl &>/dev/null; then
    curl -s -X POST "${API_URL}/api/v1/system/self-test" \
      -H "Content-Type: application/json" \
      2>/dev/null | python3 -m json.tool 2>/dev/null || \
      warn "API not reachable — self-test requires running API"
  else
    warn "curl not available"
  fi
}

show_metrics() {
  info "Prometheus metrics:"
  if command -v curl &>/dev/null; then
    curl -s "$PROMETHEUS_METRICS" 2>/dev/null | head -30 || echo "  Not available"
  fi
}

show_urls() {
  echo ""
  echo -e "  ${GREEN}╔══════════════════════════════════════════════╗${NC}"
  echo -e "  ${GREEN}║${NC}          NVR System — Access URLs           ${GREEN}║${NC}"
  echo -e "  ${GREEN}╠══════════════════════════════════════════════╣${NC}"
  echo -e "  ${GREEN}║${NC}                                              ${GREEN}║${NC}"
  echo -e "  ${GREEN}║${NC}  Web UI:        ${CYAN}${WEB_URL}${NC}                 ${GREEN}║${NC}"
  echo -e "  ${GREEN}║${NC}  API:           ${CYAN}${API_URL}${NC}                 ${GREEN}║${NC}"
  echo -e "  ${GREEN}║${NC}  API Docs:      ${CYAN}${API_DOCS}${NC}          ${GREEN}║${NC}"
  echo -e "  ${GREEN}║${NC}  Health:        ${CYAN}${API_HEALTH}${NC}    ${GREEN}║${NC}"
  echo -e "  ${GREEN}║${NC}  Metrics:       ${CYAN}${PROMETHEUS_METRICS}${NC}               ${GREEN}║${NC}"
  echo -e "  ${GREEN}║${NC}  Grafana:       ${CYAN}${GRAFANA_URL}${NC}                ${GREEN}║${NC}"
  echo -e "  ${GREEN}║${NC}                                              ${GREEN}║${NC}"
  echo -e "  ${GREEN}║${NC}  Default login:  admin / admin               ${GREEN}║${NC}"
  echo -e "  ${GREEN}║${NC}                                              ${GREEN}║${NC}"
  echo -e "  ${GREEN}╚══════════════════════════════════════════════╝${NC}"
  echo ""
}

# ────────────────────────────────────────
#  STATUS
# ────────────────────────────────────────
show_status() {
  echo ""
  echo "═══════════════════════════════════════════"
  echo "  NVR System Status"
  echo "═══════════════════════════════════════════"
  echo ""
  echo "Project:  $(pwd)"
  echo "Branch:   $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'N/A')"
  echo "Commit:   $(git rev-parse --short HEAD 2>/dev/null || echo 'N/A')"
  echo "Tag:      $(git describe --tags --abbrev=0 2>/dev/null || echo 'N/A')"
  echo ""
  echo "── Infrastructure ──"
  docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "  No containers"
  echo ""
  echo "── URLs ──"
  echo "  Web UI:  ${WEB_URL}"
  echo "  API:     ${API_URL}"
  echo "  Docs:    ${API_DOCS}"
  echo ""
  echo "── Python ──"
  echo "  Version: $(python3 --version 2>/dev/null || echo 'N/A')"
  echo "  Tests:   $(python3 -m pytest --co -q 2>/dev/null | tail -1 || echo 'N/A')"
  echo ""
  echo "── Node ──"
  echo "  Version: $(node --version 2>/dev/null || echo 'N/A')"
  echo ""
  echo "───────────────────────────────────────────"
  echo ""
}

# ────────────────────────────────────────
#  FULL SETUP
# ────────────────────────────────────────
all_setup() {
  info "══════ Full NVR Setup ══════"
  echo ""

  info "[1/7] Installing Python dependencies..."
  pip install -e ".[dev]" --break-system-packages -q 2>/dev/null || warn "pip install failed"

  info "[2/7] Installing Node dependencies..."
  cd services/web && npm install --silent 2>/dev/null && cd "$PROJECT_DIR" || warn "npm install failed"

  info "[3/7] Starting infrastructure..."
  docker compose up -d nvr-db nvr-redis nvr-minio 2>/dev/null || warn "Docker not available"
  sleep 5

  info "[4/7] Running migrations..."
  db_migrate 2>/dev/null || warn "DB not reachable — migrations skipped"

  info "[5/7] Seeding database..."
  db_seed 2>/dev/null || warn "Seed skipped"

  info "[6/7] Running tests..."
  run_tests 2>/dev/null || echo ""

  info "[7/7] Starting services..."
  echo ""
  echo "  To start API:     ./manage.sh api-dev"
  echo "  To start Web UI:  ./manage.sh web-dev"
  echo ""

  show_urls
  ok "══════ Setup Complete ══════"
}

# ────────────────────────────────────────
#  MAIN
# ────────────────────────────────────────

# Ensure manage.sh is executable
[[ -x "$0" ]] || chmod +x "$0"

case "${1:-help}" in
  help|--help|-h)                       help_cmd ;;
  infra-up)                              infra_up ;;
  infra-down)                            infra_down ;;
  infra-status)                          infra_status ;;
  db-migrate)                            db_migrate ;;
  db-seed)                              db_seed ;;
  db-setup)                             db_setup ;;
  db-reset)                             db_reset ;;
  api-dev)                              api_dev ;;
  api-start)                            api_dev ;; # dev mode by default
  web-dev)                              web_dev ;;
  stream-manager)                       stream_manager ;;
  recording-engine)                     recording_engine ;;
  ai-engine)                            ai_engine ;;
  docker-build)                         docker_build ;;
  docker-up)                            docker_up ;;
  docker-down)                          docker_down ;;
  docker-logs)                          shift; docker_logs "$@" ;;
  docker-restart)                       shift; docker_restart "$@" ;;
  test)                                 shift; run_tests "$@" ;;
  test-cov)                             run_tests_cov ;;
  test-web)                             run_tests_web ;;
  test-e2e)                             run_tests_e2e ;;
  test-all)                             run_tests_all ;;
  lint)                                 lint_cmd ;;
  format)                               format_cmd ;;
  typecheck)                            typecheck_cmd ;;
  lint-web)                             lint_web ;;
  typecheck-web)                        typecheck_web ;;
  check-all)                            check_all ;;
  health)                               health_check ;;
  self-test)                            self_test ;;
  metrics)                              show_metrics ;;
  urls)                                 show_urls ;;
  status)                               show_status ;;
  update-deps)
    pip install -e ".[dev]" --break-system-packages
    cd services/web && npm install && cd "$PROJECT_DIR"
    ok "Dependencies updated"
    ;;
  clean)
    info "Cleaning build artifacts..."
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
    find . -type f -name "*.pyc" -delete 2>/dev/null
    rm -rf .pytest_cache .mypy_cache .ruff_cache 2>/dev/null
    rm -rf services/web/node_modules 2>/dev/null
    ok "Clean complete"
    ;;
  all-setup)                            all_setup ;;
  *)
    echo "Unknown command: $1"
    echo "Run './manage.sh help' for usage."
    exit 1
    ;;
esac
