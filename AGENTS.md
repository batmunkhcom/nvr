# AGENTS.md — AI Development Guidelines for NVR System

## Project: NVR (Network Video Recorder) System

A comprehensive, production-grade NVR system for managing diverse IP cameras
(ONVIF, RTSP, vendor-specific) with AI-powered detection, recording, multi-storage,
and web-based monitoring.

---

## Core Principles for AI Agents

### 1. Single Source of Truth — ЗӨВХӨН МЭДЭЭЛЛИЙН САН

**Энэ төсөлд HARDCODE юм БАЙХГҮЙ.** Бүх тохиргоо зөвхөн мэдээллийн санд хадгалагдана.

- `config/default.yml` нь зөвхөн **анхны DB seed-д л** ашиглагдана. Дараа нь хэзээ ч уншигдахгүй.
- API, service хоорондын URL, port, credential — **бүгд DB-ээс уншигдана**.
- Камерын RTSP URL, username/password, storage path — **DB**.
- Хэрэв ямар нэг утгыг файлд бичих шаардлага гарвал — **энэ нь буруу**. DB schema-д талбар нэмж, API-аар удирдах ёстой.

```python
# БУРУУ ❌ (юм hardcode хийж болохгүй)
MAIN_STREAM_PATH = "/Streaming/Channels/101"
STORAGE_ROOT = "/data/recordings"
CONFIG = yaml.safe_load(open("config.yml"))

# ЗӨВ ✅
config = await db.fetch_system_config("storage.default_path")
camera = await db.fetch_camera(camera_id)
stream_uri = camera.stream_main_uri
```

### 2. Schema-First Development

- **API өөрчлөхөөс өмнө** Pydantic schema засварла.
- **DB өөрчлөхөөс өмнө** SQLAlchemy model засварла, Alembic migration үүсгэ.
- API endpoint бүр request/response schema-тай байх ёстой.
- OpenAPI документаци нь үргэлж schema-аас auto-generated байх ёстой.

### 3. Asynchronous I/O Everywhere

- FastAPI route handler бүр `async def` байх.
- SQLAlchemy `AsyncSession` ашиглах.
- Redis `aioredis` / `redis.asyncio` ашиглах.
- FFmpeg subprocess — `asyncio.create_subprocess_exec`.
- CPU-intensive ажиллагаа (AI inference) — `run_in_executor` эсвэл тусдаа worker процесс.

### 4. Service Layer Separation

API route handler — **thin wrapper**. Бүх бизнес логик **service** давхаргад:

```
app/api/v1/cameras.py     →  зөвхөн HTTP request/response handling
app/services/camera_service.py →  бүх бизнес логик энд
```

Хэзээ ч route handler дотор шууд DB query, FFmpeg command, file I/O бичиж болохгүй.

### 5. Database Migrations (Alembic)

- Model өөрчлөх болгонд `alembic revision --autogenerate` ажиллуул.
- Migration файлыг гараар шалгаж, шаардлагатай бол засварла.
- Down migration **БҮГД** бичих ёстой.
- Migration commit хийхээс өмнө `alembic upgrade head` + `alembic downgrade -1` туршиж үз.
- **Migration naming**: Alembic auto-generate + commit-д ойлгомжтой тайлбар (`-m "add_camera_audio_capabilities"`).

### 6. Error Handling & Logging

- Бүх алдаа structured JSON log-оор гарах ёстой.
- Exception swallowing хийж болохгүй (except Exception: pass гэх мэт).
- FastAPI exception handler global level дээр тохируулсан.
- Service тус бүр `structlog` / `logging` module ашиглах.
- Алдаа бүр trace ID-тэй байх.
- **Full traceback logging**: Үргэлж `logger.error("...", exc_info=True)` — `logger.error("...: %s", e)` хэзээ ч битгий хэрэглэ. `str(e)` хоосон үед traceback алга болдог.

```python
import structlog
logger = structlog.get_logger()

try:
    result = await some_operation()
except SomeError as e:
    logger.error("operation_failed", error=str(e), camera_id=camera_id, exc_info=True)
    raise
```

### 7. Testing Requirements

**Бичих код болгонд тест бичнэ.**

- Unit test — service layer logic.
- Integration test — API endpoint + DB.
- `pytest` + `pytest-asyncio` + `httpx.AsyncClient`.
- Test database — тусдаа PostgreSQL container, migration хийгдсэн.
- Factory boy / fixtures ашиглан тестийн өгөгдөл үүсгэх.
- Coverage target: **>80%** line coverage.

**Тест бичихгүйгээр код commit хийж болохгүй.**

```bash
pytest -v --cov=services --cov-report=term-missing
pytest services/api/tests/ -v --cov
pytest -k "camera" -v                       # Filter by keyword
pytest -m "not integration"                 # Skip slow tests
```

### 8. Camera Auto-Discovery — Smart Engine

Камер нэмэх үед **auto-discovery engine** ажиллах ёстой. Discovery нь дараах дарааллаар:

1. **ONVIF WS-Discovery** (multicast) — хамгийн найдвартай
2. **Subnet IP scan** → RTSP port probe (554) → OPTIONS / DESCRIBE
3. **HTTP server header** шинжилгээ → vendor fingerprinting
4. **ARP table + MAC OUI lookup** → үйлдвэрлэгч таних
5. **Vendor-specific broadcast** (Hikvision UDP, Dahua UDP, Axis mDNS)
6. **mDNS/Avahi** query

Олдсон камеруудыг **confidence score** (0-100)-тай буцааж, хэрэглэгчид харуулна.
Discovery процесс нь **background task** (FastAPI BackgroundTasks) хэлбэрээр ажиллана.

`services/stream-manager/app/discovery/fingerprint.py` файлд vendor fingerprint database бий.
Vendor бүрийн таних шинж:
- MAC OUI prefix
- HTTP Server header
- RTSP path patterns
- ONVIF manufacturer string
- Default credentials

### 9. Code Style — Python

```python
# Imports — absolute, sorted: stdlib → third-party → internal
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.camera import Camera
from app.schemas.camera import CameraResponse
from app.services.camera_service import CameraService

# Type annotations — БҮХ функцийн параметр болон return утга
async def get_camera(camera_id: UUID, db: AsyncSession) -> CameraResponse:
    ...

# Docstrings — Google style
async def get_camera(camera_id: UUID, db: AsyncSession) -> CameraResponse:
    """Fetch a single camera by its UUID.

    Args:
        camera_id: Camera unique identifier.
        db: Database session.

    Returns:
        CameraResponse with all camera details.

    Raises:
        HTTPException(404): Camera not found.
    """
    ...

# Dataclass / Pydantic models for internal data
from pydantic import BaseModel

class CameraCreate(BaseModel):
    name: str
    ip_address: IPvAnyAddress
    username: str | None = None
    password: str | None = None
```

### 10. Code Style — TypeScript (React)

```typescript
// Imports — absolute paths (@/ alias)
import { useQuery } from '@tanstack/react-query';
import { Camera } from '@/types';
import { apiClient } from '@/api/client';

// Interfaces — бүх props, state, API response
interface CameraGridProps {
  cameras: Camera[];
  onCameraSelect: (id: string) => void;
}

// Hooks — custom hook-д логик төвлөрүүлэх
const useCameras = () => {
  return useQuery({
    queryKey: ['cameras'],
    queryFn: () => apiClient.get<Camera[]>('/api/v1/cameras'),
  });
};
```

### 11. Git Workflow

- **main branch** — production-ready код.
- **Feature branch** — `feature/description` эсвэл `fix/description`.
- **Commit message** — Conventional Commits формат:
  - `feat: add ONVIF camera discovery endpoint`
  - `fix: handle camera connection timeout gracefully`
  - `refactor: extract storage backend to abstract class`
  - `test: add integration tests for recording engine`
  - `docs: update API documentation for storage endpoints`
- PR үүсгэхээс өмнө **lint + typecheck + test** гурвыг бүгдийг нь амжилттай ажиллуулсан байх.

**Version Tagging — COMMIT БҮРТ tag үүсгэнэ:**

```
v<MAJOR>.<MINOR>.<PATCH>-<SHORT_HASH>

Жишээ:
  v0.00.01-a3f2c1b    # Эхний commit
  v0.01.00-d4e5f6a    # Phase 1 дууссаны дараа
  v0.01.04-b7c8d9e    # Bug fix
  v1.00.00-e1f2a3b    # Production release

Дүрэм:
  MAJOR: Breaking changes эсвэл phase дуусахад (0→1, 1→2...)
  MINOR: Шинэ feature нэмэхэд
  PATCH: Bug fix, refactor (ихэнх commit)
  SHORT_HASH: `git rev-parse --short HEAD` (эхний 7 тэмдэгт)

Tag үүсгэх:
  git tag -a "v0.00.XX-$(git rev-parse --short HEAD)" -m "commit message"
```

### 12. Docker & Environment

- Бүх үйлчилгээ `docker-compose.yml` дотор тодорхойлогдсон.
- Хөгжүүлэлтийн үед: `docker compose up api db redis minio`
- Production: `docker compose -f docker-compose.prod.yml up -d`
- Environment variables — `.env` файлд. Жинхэнэ нууц утгууд `.env.example` дотор байхгүй.
- Docker image tag — `git rev-parse --short HEAD` commit hash.
- **Бүх container_name префикс:** `nvr-` (жишээ: `nvr-api`, `nvr-stream-manager`, `nvr-db`)

### 13. Before Committing — Checklist

Код өөрчлөлт бүрийн өмнө дараахыг гүйцэтгэх:

- [ ] `ruff check services/` — Python lint passes
- [ ] `ruff format --check services/` — Python formatting correct
- [ ] `mypy services/` — Type checking passes (төсөл тохируулсны дараа)
- [ ] `pytest -v` — All tests pass
- [ ] `eslint src/` — TypeScript lint passes (web үйлчилгээнд өөрчлөлт орсон бол)
- [ ] `tsc --noEmit` — TypeScript type check passes
- [ ] `docker compose build` — Docker image build successful
- [ ] Alembic migration байгаа эсэх (DB model өөрчлөгдсөн бол)
- [ ] `gitleaks detect --no-git` — Нууц мэдээлэл алдагдаагүй эсэх (secret scan)
- [ ] **500 line limit** — Шинэ/өөрчлөгдсөн файл бүр ≤500 мөр
- [ ] **Version tag** — `git tag -a "v..."` үүсгэсэн эсэх

### 14. Security Rules

- **Хэзээ ч** password, API key, secret, token, `.env` файл commit хийж болохгүй.
- Камерын password — DB-д AES-256-GCM encryption-тай хадгалагдана.
- JWT secret — зөвхөн environment variable эсвэл Docker secret.
- API key — hash хэлбэрээр хадгалагдана (bcrypt), raw key зөвхөн үүсгэх үед л харагдана.
- SQL injection-с хамгаалах — зөвхөн parameterized query / ORM.
- User input бүр validation давхардсан байх (Pydantic + FastAPI param validation).
- **Pre-commit secret scan**: `gitleaks` hook суулгасан. Commit хийхээс өмнө scan хийгдэнэ.
- `.env`, `*.pem`, `*.key`, `credentials.*`, `*.pfx` — бүгд `.gitignore`-д байх ёстой.

### 15. Runtime Commands

```bash
# Development
docker compose up -d db redis minio         # Start infrastructure
cd services/api && uvicorn app.main:app --reload  # Start API dev server
cd services/web && npm run dev              # Start React dev server

# Database
alembic upgrade head                        # Apply migrations
alembic revision --autogenerate -m "desc"   # Create migration

# Testing
pytest -v                                   # All tests
pytest services/api/tests/ -v --cov         # API tests with coverage

# Linting
ruff check services/                        # Python lint
ruff format --check services/               # Python format check
cd services/web && npx eslint src/          # TypeScript lint

# Docker builds
docker compose build                        # Build all services
docker compose up -d                        # Run all services

# Pre-commit hook setup
make setup-hook                             # Install git hooks (secret scan + naming guard)
```

---

## Critical Rules (New)

### 16. File Size Limit — MAX 500 Lines

**Hard limit**: **MAX 500 lines per file** for all source code files (`*.py`, `*.ts`, `*.tsx`, `*.sql`).

Exceptions: auto-generated files (`package-lock.json`, build artifacts), configuration data files where splitting would break tooling.

#### When Creating New Code

1. If a new module/component would exceed 500 lines, **SPLIT IT before creating**
2. Extract helper functions → separate utility file (`_helpers.py`, `_utils.ts`)
3. Extract data/constants → separate data file (`_data.py`, `_constants.ts`)
4. Extract sub-components → separate component files
5. Extract hooks/logic → separate hook files (`use*.ts`)

#### When Modifying Existing Code

1. If a file is approaching 500 lines, extract new code into appropriate sub-modules
2. Never add to an already bloated file (>500 lines)
3. When modifying a >500 line file, **first split it, then make changes**

#### Split Patterns — Python

```
app/api/v1/cameras.py          # Route handlers (≤500 lines)
app/api/v1/cameras_shared.py   # Shared: imports, DB deps, models, helper funcs
app/api/v1/cameras_pydantic.py # Separate Pydantic models from logic

app/services/camera_service.py       # Core business logic
app/services/camera_service_ptz.py   # PTZ-specific logic
app/services/camera_service_audio.py # Audio/talkback logic
```

#### Split Patterns — TypeScript/React

```
src/components/camera/CameraGrid.tsx     # Grid component
src/components/camera/CameraCard.tsx     # Individual card
src/components/camera/CameraDetail.tsx   # Detail modal
src/components/camera/CameraFilters.tsx  # Filter bar

src/hooks/useCameras.ts        # Camera data + CRUD
src/hooks/useCameraLive.ts     # Live stream WebSocket

src/pages/tabs/Dashboard.tsx   # Multi-view grid
src/pages/tabs/Recordings.tsx  # Recording browser
src/pages/tabs/Timeline.tsx    # Timeline player
```

#### Verification

```bash
# Check for violations
find . -name "*.py" -path "*/services/*" | xargs wc -l | sort -rn | head -10
find . -name "*.ts" -o -name "*.tsx" | grep -v node_modules | xargs wc -l | sort -rn | head -10

# Verify a specific file
wc -l path/to/file.py   # MUST be ≤ 500
```

---

### 17. Circuit Breaker & Resilience Rules

NVR систем нь сүлжээний камер, storage backend, FFmpeg subprocess зэрэг **гадаад тогтворгүй нөөцүүдтэй** ажилладаг. Найдвартай ажиллагааг хангахын тулд circuit breaker заавал байх ёстой.

#### Mandatory Timed Auto-Reset

- **БҮХ circuit breaker** дээр заавал timed cooldown auto-reset байх ёстой. Хэзээ ч manual-only reset байж болохгүй.
- Pattern: `circuit_open_until = now + timedelta(seconds=cooldown)`
- Cooldown: эхний 60s, exponential backoff (×2 per trip, max 600s)
- `_is_circuit_open()` — `circuit_open_until < now` бол auto-reset

```python
class CircuitBreaker:
    def __init__(self, name: str, base_cooldown: int = 60, max_cooldown: int = 600):
        self.name = name
        self.base_cooldown = base_cooldown
        self.max_cooldown = max_cooldown
        self.trip_count = 0
        self.circuit_open_until: float = 0.0

    async def _is_circuit_open(self) -> bool:
        if self.circuit_open_until > time.time():
            return True
        if self.circuit_open_until > 0 and time.time() >= self.circuit_open_until:
            logger.info("circuit_auto_reset", name=self.name)
            self.circuit_open_until = 0.0
        return False

    def trip(self):
        cooldown = min(self.base_cooldown * (2 ** self.trip_count), self.max_cooldown)
        self.trip_count += 1
        self.circuit_open_until = time.time() + cooldown
        logger.warning("circuit_tripped", name=self.name, cooldown_s=cooldown, trip_count=self.trip_count)

    def reset(self):
        self.trip_count = 0
        self.circuit_open_until = 0.0

# ХЭЗЭЭ Ч ИНГЭЖ БОЛОХГҮЙ ❌
# if self.error_count > 5: return "circuit_open"  # manual only, stuck forever!

# ЗААВАЛ ИНГЭХ ЁСТОЙ ✅
# if self._is_circuit_open(): raise CircuitOpenError(name, cooldown_remaining)
```

#### Where Circuit Breakers Are Required

| Component | Breaker for | Cooldown |
|---|---|---|
| Stream Manager | FFmpeg subprocess crash (per camera) | 60s → 600s |
| Recording Engine | Storage backend write failure | 120s → 600s |
| AI Engine | ONNX inference timeout | 30s → 300s |
| Camera Manager | RTSP connection failure (per camera) | 30s → 300s |
| ONVIF Scanner | ONVIF service call timeout | 120s → 600s |
| Notification Svc | Email/Webhook delivery failure | 300s → 3600s |

---

### 18. Component Lifecycle & Zombie Prevention

FFmpeg subprocess, AI inference worker, background task-ууд нь **zombie процесс** болох өндөр эрсдэлтэй.

#### Mandatory Patterns (ALL restartable components):

##### 1. Singleton Enforcement

```python
_instance_count: int = 0

async def start(self):
    global _instance_count
    if _instance_count > 0:
        logger.warning("component_already_running", count=_instance_count)
        await self._cancel_previous_instance()
    _instance_count += 1
    self._running = True
    self._task = asyncio.create_task(self._run())

async def stop(self):
    self._running = False
    if self._task:
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
    global _instance_count
    _instance_count = max(0, _instance_count - 1)
```

##### 2. Subtask Cleanup (Critical for FFmpeg!)

```python
# БУРУУ ❌ — return_exceptions=True CancelledError-г иддэг
results = await asyncio.gather(*subtasks, return_exceptions=True)

# ЗӨВ ✅ — тусдаа task, cancel хийхэд бүгд зогсоно
self._subtasks = [asyncio.create_task(t) for t in subtasks]
try:
    await asyncio.gather(*self._subtasks)
finally:
    for task in self._subtasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*self._subtasks, return_exceptions=True)
```

##### 3. FFmpeg Subprocess Cleanup

```python
async def _kill_ffmpeg(self, process: asyncio.subprocess.Process):
    """Graceful shutdown: SIGTERM → wait → SIGKILL."""
    try:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
    except ProcessLookupError:
        pass  # Already dead
    logger.info("ffmpeg_subprocess_stopped", pid=process.pid)
```

##### 4. Restart Cooldown

```python
_last_restart_at: float = 0.0
RESTART_COOLDOWN: int = 600  # 10 minutes

async def start(self):
    if time.time() - self._last_restart_at < self.RESTART_COOLDOWN:
        logger.warning("restart_cooldown_active", remaining_s=self.RESTART_COOLDOWN - (time.time() - self._last_restart_at))
        return
    self._last_restart_at = time.time()
    # ... proceed with start
```

##### 5. Inner Timeout

```python
async def _run_cycle(self):
    try:
        await asyncio.wait_for(self._do_work(), timeout=90.0)
    except asyncio.TimeoutError:
        logger.error("cycle_timeout", component=self.name, exc_info=True)
        await self._cleanup_hung_operations()
```

---

### 19. Zombie Detection & Debugging

Zombie процесс илрүүлэх командууд:

```bash
# FFmpeg zombie байгаа эсэх — нэг камераас олон FFmpeg процесс
docker exec nvr-stream-manager ps aux | grep ffmpeg | wc -l
# Хэрэв камерын тооноос олон бол → zombie байна

# Cycle дупликат байгаа эсэх
docker logs nvr-stream-manager | grep "Cycle:" | tail -20
# Нэг 30s интервалд 1-ээс олон "Cycle:" гарвал → zombie байна

# Restart хэт олон байгаа эсэх
docker logs nvr-stream-manager | grep "restarted.*stream_manager" | wc -l
# цагт 3-аас дээш бол → restart loop байна

# Storage backend алдаа
docker logs nvr-recording-engine | grep "storage.*error" | tail -20

# DB connection pool exhaustion
docker logs nvr-api | grep "QueuePool.*exhausted" | tail -10
```

---

### 20. NVR-Specific Engineering Rules

#### FFmpeg Process Management

- **Process per camera** — нэг камерт нэг FFmpeg subprocess (main + sub stream бол салгах)
- **Graceful shutdown**: SIGTERM → 5s wait → SIGKILL
- **Memory monitoring**: FFmpeg процесс нь >1GB RAM хэрэглэвэл restart
- **Atomic recording segments**: FFmpeg-г `-f segment -segment_format mp4 -segment_time 900` ашиглах
- **Corrupt segment recovery**: `ffmpeg -err_detect ignore_err -i corrupted.mp4 -c copy recovered.mp4`

#### Camera Reconnection Strategy

```python
# Exponential backoff with jitter for camera reconnection
async def reconnect_camera(camera_id: UUID):
    backoff = 1.0  # seconds
    max_backoff = 300.0
    for attempt in range(100):  # ~8 hours max
        try:
            await stream_manager.connect(camera_id)
            return
        except ConnectionError:
            jitter = random.uniform(0, backoff * 0.5)
            await asyncio.sleep(backoff + jitter)
            backoff = min(backoff * 2, max_backoff)
```

#### Storage Tier Migration Safety

- **Atomic move**: Эхлээд destination руу copy → verify checksum → source устгах. Хэзээ ч move (rename) хийж болохгүй (cross-filesystem эрсдэл).
- **Crash recovery**: `storage_tier_migration` хүснэгт дээр pending state хадгалах. Startup үед дутуу migration-ийг resume.

#### Disk Space Emergency Protocol

```python
# Storage 95% дүүрсэн үед — aggressive cleanup
async def emergency_cleanup(storage_backend):
    free_pct = await storage_backend.free_percent()
    if free_pct < 5:
        logger.critical("disk_space_critical", free_pct=free_pct)
        # 1. Oldest continuous recordings delete
        await delete_oldest_continuous_recordings(storage_backend, keep_hours=24)
        # 2. Event snapshots хуучин зүйлс
        await delete_oldest_snapshots(storage_backend, keep_days=7)
        # 3. Still critical → delete all non-event recordings
        if await storage_backend.free_percent() < 3:
            await delete_all_continuous_recordings(storage_backend)
```

#### Stream Protocol Auto-Fallback

Камер бүрт RTSP transport protocol эхлээд TCP-ээр оролдох, амжилтгүй бол UDP, цаашлаад HTTP tunneling:

```python
TRANSPORT_FALLBACK_ORDER = ["tcp", "udp", "http"]
# DB-д camera.stream_transport талбарт хадгална
# FFmpeg: -rtsp_transport {transport}
```

---

### 21. Version Tagging — Enforcement

**Commit БҮРД version tag үүсгэх ёстой.** Pre-commit hook check + post-commit auto-tag.

```bash
# Post-commit hook (auto-apply after commit):
# Reads version from pyproject.toml (v0.00.XX)
# Increments PATCH automatically per commit
# Creates: v0.00.XX-<short_hash>

# Manual tag for MINOR/MAJOR bumps:
git tag -a "v0.01.00-$(git rev-parse --short HEAD)" -m "Phase 2: Camera integration complete"
git tag -a "v1.00.00-$(git rev-parse --short HEAD)" -m "Production release"

# Tag naming regex: ^v\d+\.\d{2}\.\d{2}-[a-f0-9]{7}$
```

---

### 22. Pre-commit Hooks

Суулгах: `make setup-hook` (или `./scripts/setup-hooks.sh`)

Дараах шалгалтыг commit-ийн өмнө гүйцэтгэнэ:

| Hook | Check |
|---|---|
| `secret-scan` | `gitleaks detect --no-git` — нууц мэдээлэл алдагдаагүй эсэх |
| `naming-guard` | `container_name` бүр `nvr-` префикстэй эсэх |
| `line-count` | Шинэ файлууд 500 мөрөөс хэтрээгүй эсэх |
| `version-tag` | Commit message дотор `[skip-tag]` байхгүй бол tag auto-create |

---

## Project Files Reference

| File | Purpose |
|---|---|
| `docs/PLAN.md` | Бүрэн архитектур төлөвлөгөө, API spec, DB schema |
| `config/vendor_patterns.yml` | Камер үйлдвэрлэгч таних fingerprint DB (11 vendor) |
| `config/default.yml` | Анхны системийн тохиргоо (DB seed only) |
| `services/api/app/core/config.py` | Runtime тохиргоо (DB-ээс унших) |
| `services/api/app/models/` | SQLAlchemy ORM models |
| `services/api/app/schemas/` | Pydantic request/response schemas |
| `services/api/app/services/` | Business logic layer |
| `services/stream-manager/app/discovery/` | Camera auto-discovery engine (6 phases) |
| `scripts/setup-hooks.sh` | Pre-commit hook installer |
| `scripts/seed_db.py` | Initial configuration seeder |

---

*Хамгийн чухал дүрэм: Энэ төслийн кодод HARDCODE утга (URL, port, path, credential, API key) БАЙХГҮЙ. Бүгд мэдээллийн сангаас уншигдана.*
