# NVR System Security Audit Report

**Date:** 2026-07-28
**Auditor:** mBm AI Assistant
**Scope:** Full system — API, AI Engine, Recording Engine, Stream Manager, Web Frontend, Docker Infrastructure

---

## CRITICAL (6)

### C1. Hardcoded JWT secret in config defaults
**File:** `services/api/app/core/config.py:61`
```python
jwt_secret_key: str = "dev_secret_change_me"
```
`JWT_SECRET_KEY` env-г тохируулаагүй үед мэдэгдэж буй default утгаар JWT токен үүсгэнэ. Repository-д хандсан хэн ч хүчинтэй токен үүсгэх боломжтой.
**Fix:** Default-г устгах. Env тохируулаагүй бол startup дээр crash хийх эсвэл random per-process secret үүсгэх.

### C2. SQL injection pattern — counter_service.py
**File:** `services/api/app/services/counter_service.py:31-43`
```python
where = ""
if camera_id:
    where = "AND camera_id = CAST(:camera_id AS uuid)"
result = await db.execute(text(f"""...WHERE ... {where}..."""), params)
```
Утгууд нь параметрчлагдсан (safe) боловч WHERE clause-г string concatenation-оор бүтээж байгаа хэв маяг нь эмзэг.
**Fix:** SQLAlchemy ORM `select.where()` ашиглах эсвэл бүх WHERE нөхцөлийг параметрчлах.

### C3. SQL injection — lpr_service.py WHERE clause
**File:** `services/api/app/services/lpr_service.py:20-48`
C2-той ижил хэв маяг: `where_parts` list-д string concatenation хийж SQL бүтээж байна. Утгууд параметрчлагдсан ч бүтэц эмзэг.

### C4. SQL injection — network.py f-string интерполяци
**File:** `services/api/app/api/v1/network.py:125-134, 178-190, 288-296`
```python
bucket = "minute" if range in ("1h", "6h", "12h") else "hour"
result = await db.execute(text(f"SELECT date_trunc('{bucket}', ..."))
```
`bucket` controlled map-аас гарч байгаа тул одоогоор safe. Гэхдээ f-string SQL интерполяцийн хэв маяг эмзэг.

**File:** `services/api/app/api/v1/network.py:669-677`
```python
updates = {k: v for k, v in body.items() if k in allowed_fields}
set_clause = ", ".join(f"{k} = :{k}" for k in updates)
```
`allowed_fields` fixed set-ээс гарч байгаа тул safe. Гэхдээ тохируулга алдахад SQL injection-д хүргэх эрсдэлтэй.

### C5. AI model алга — detection чимээгүй ажиллахгүй
**File:** `services/ai-engine/app/main.py:222-226`
YOLO model байхгүй үед system чимээгүйхэн detection-гүй ажиллана. Хэрэглэгч хэдэн өдөр мэдэхгүй байж болзошгүй.
**Fix:** Missing model үед health check FAIL хийх, alert харуулах.

### C6. Stream-manager-т RTSP URI (нууц үгтэй) HTTP-ээр дамжуулдаг
**File:** `services/ai-engine/app/main.py:137-140`
```python
httpx.post(f"{_STREAM_MANAGER_URL}/relay/start",
    json={"rtsp_uri": authed_uri, ...})
```
Камерын нууц үг агуулсан RTSP URI HTTP-ээр stream-manager луу илгээгдэнэ. Docker network дотор аюулгүй ч plaintext дамжуулалт анхаарал татахуйц.

---

## HIGH (6)

### H1. CORS allow_credentials=True + allow_origins=["*"]
**File:** `services/api/app/middleware/cors.py:10-15`
```python
allow_origins=["*"], allow_credentials=True
```
Ямар ч вэбсайтаас authenticated хүсэлт илгээх боломжтой (хэдийгээр cookie биш Bearer token ашигладаг ч аюултай тохиргоо).

### H2. JWT HS256 (symmetric) algorithm
**File:** `services/api/app/core/config.py:62`
HS256 алгоритм — нэг түлхүүрээр үүсгэж, шалгадаг. Multi-service deployment-д RS256 илүү тохиромжтой.

### H3. Нууц үгийн нарийн түвэгтэй байдлын шалгалт байхгүй
**File:** `services/api/app/api/v1/users.py:60-67`
`create_user`, `change_password` — 1 тэмдэгттэй нууц үгийг ч хүлээн авна. Хамгийн бага урт, төвөгтэй байдлын шаардлага байхгүй.

### H4. Account lockout механизм байхгүй
**File:** `services/api/app/middleware/rate_limit.py:14-16`
Login 5/60s-аар хязгаарлагдсан ч энэ нь IP-д суурилсан. Distributed brute-force ашиглан олон IP-ээр халдахад account түгжигдэхгүй.

### H5. In-memory rate limiter — worker хооронд хуваалцагдаагүй
**File:** `services/api/app/middleware/rate_limit.py:22`
```python
_history: dict[str, list[float]] = defaultdict(list)
```
Worker бүр өөрийн тоологчтой. 4 worker-тэй үед attacker 4 дахин их хүсэлт илгээх боломжтой. Redis-рүү шилжүүлэх хэрэгтэй.

### H6. RTSP URL-д password encoding асуудал
**File:** `services/ai-engine/app/frame_sampler.py:133-142`
`build_rtsp_url()` — URL encode хийхдээ тусгай тэмдэгтүүдийг зөв кодлодог ч RTSP-ийн зарим сервер URL encoding-г дэмждэггүй.

---

## MEDIUM (8)

### M1. Unauthenticated endpoint-үүд
| Endpoint | Файл | Тайлбар |
|----------|------|---------|
| `GET /` | `services/api/app/main.py:77` | Root — standard |
| `GET /api/v1/system/health` | `system.py:31` | Health check — standard |
| `GET /api/v1/system/recording/status` | `system.py:111` | ⚠️ Recording paused эсэх мэдээлэл — мэдээлэл алдагдах эрсдэл |
| `GET /api/v1/ai/health` | `ai.py:175` | AI engine status — benign |
| `GET /metrics` | `main.py:82` | Prometheus metrics — standard |

### M2. Token query string-д дамжуулагддаг (шаардлагатай ч дутагдалтай)
**File:** `services/api/app/middleware/auth.py:16`
`?token=` query param — img/video элементүүд `Authorization` header илгээж чаддаггүй тул зайлшгүй. Гэхдээ токен URL-д байх нь proxy/server лог, browser history, Referer header-р ил гардаг. Short-lived scoped token ашиглах хэрэгтэй.

### M3. Refresh token rotation — хуучин токен хүчингүй болдоггүй
**File:** `services/api/app/api/v1/auth.py:92-93`
Token refresh бүрт шинэ refresh token үүсгэдэг ч хуучин токенийг хүчингүй болгодоггүй. Token хулгайд алдвал халдагч + хууль ёсны хэрэглэгч хоёулаа хязгааргүй refresh хийх боломжтой.

### M4. CSRF protection байхгүй
Cookie-based auth байхгүй тул одоогоор CSRF аюулгүй. Хэрэв ирээдүйд cookie auth нэмбэл CSRF token заавал хэрэгтэй.

### M5. `NVR_ENCRYPTION_KEY` урт шалгалтгүй
**File:** `services/api/app/core/security.py:54`, `packages/common/nvr_common/security.py:14`
Base64 decode хийхдээ уртыг шалгадаггүй. Буруу түлхүүр өгвөл чимээгүйхэн ажиллахгүй болно.

### M6. FFmpeg subprocess concurrency хязгааргүй
**File:** `services/api/app/api/v1/snapshot.py:71-89`
Snapshot авах үед хэрэглэгч бүрт FFmpeg процесс үүсгэдэг. Concurrency хязгаарлалт байхгүй.

### M7. Dahua camera — MD5 digest auth
**File:** `services/api/app/services/camera_service.py:403-404`
HTTP Digest auth-д MD5 ашигладаг — стандартаар шаардлагатай ч MD5 хуучин, сул алгоритм.

### M8. `last_login_at` атомар бус шинэчлэл
**File:** `services/api/app/api/v1/auth.py:54-55`
`flush()` амжилтгүй бол login амжилттай ч `last_login_at` шинэчлэгдэхгүй. Бага нөлөөтэй.

---

## LOW (11)

### L1. Хамгийн бага нууц үгийн уртын шалгалт байхгүй
**File:** `services/api/app/schemas/user.py` — `UserCreate` schema-д `min_length` тохируулаагүй.

### L2. Docker container-ууд root-оор ажилладаг
Бүх Dockerfile (`docker/api/Dockerfile`, `docker/ai-engine/Dockerfile`, `docker/recording-engine/Dockerfile`) root хэрэглэгчээр ажиллана. Least-privilege зарчим зөрчигдсөн.

### L3. DB болон Redis порт хостод нээлттэй
```yaml
ports:
  - "5432:5432"   # PostgreSQL
  - "6379:6379"   # Redis
```
Зөвхөн development орчинд хэрэгтэй. Production орчинд хаах хэрэгтэй.

### L4. MediaMTX API, publish, playback — бүгдэд нээлттэй
**File:** `config/mediamtx.yml:18-30`
```yaml
authInternalUsers:
  - user: any
    permissions: [publish, read, playback, api, metrics]
```
Ямар ч хэрэглэгч MediaMTX API-г удирдах, stream нийтлэх, тоглуулах боломжтой.

### L5. `.env` development нууц үгнүүд
`.env` файлд `POSTGRES_PASSWORD=nvr_dev_password_change_me`, `JWT_SECRET_KEY=nvr_dev_secret_...` зэрэг development credential-ууд байгаа. `.gitignore`-д байгаа эсэхийг шалгах.

### L6. Timezone string аюулгүй боловсруулалт
**Файл:** `services/api/app/services/config_service.py:36-43`
```python
def get_timezone(db: AsyncSession) -> ZoneInfo:
    tz_str = str(await get_config_value(db, "ui.timezone", _DEFAULT_TZ))
    try:
        return ZoneInfo(tz_str)
    except ZoneInfoNotFoundError:
        return ZoneInfo(_DEFAULT_TZ)
```
`ZoneInfo()` IANA database-р баталгаажуулдаг тул аюулгүй. Буруу утга fallback-руу шилжинэ.

### L7. `read_config_str` буцаах утга sanitize хийгдээгүй
**Файл:** `services/ai-engine/app/db.py:75-84`
Хэрэглэгчийн оруулсан утгыг шууд буцаана. `ZoneInfo()` дотор exception handling хийгдсэн тул crash хийхгүй.

### L8. Error response stack trace ил гаргадаггүй
**Файл:** `services/api/app/main.py:60-74`
Global exception handler — алдааны мэдээллийг `"Internal server error"` гэж нууцлана. Зөв.

### L9. `update_camera_config` — column name шалгалт
**Файл:** `services/api/app/api/v1/network.py:651-677`
`allowed_fields` fixed set-ээр column name-с шалгадаг. SQL injection-с хамгаалсан.

### L10. `create_subprocess_exec` — shell injection-с хамгаалсан
**Файл:** `services/api/app/api/v1/snapshot.py:71-89`
`create_subprocess_exec` тусдаа аргументуудаар дуудагддаг тул shell injection-д өртөхгүй.

### L11. Event cleanup — параметрчлагдсан query
**Файл:** `services/api/app/api/v1/events.py:152-155`
`cutoff`, `camera_id` параметрчлагдсан. WHERE clause string concatenation ашигласан ч утгууд bound parameter.

---

## Нэн тэргүүнд засах 3 асуудал

| # | Асуудал | Файл | Ноцтой байдал |
|---|---------|------|---------------|
| 1 | Hardcoded `jwt_secret_key` default-г устгах | `api/app/core/config.py:61` | **CRITICAL** |
| 2 | SQL injection pattern-уудыг ORM `select.where()` болгох | `counter_service.py`, `lpr_service.py`, `network.py`, `events.py` | **CRITICAL** |
| 3 | Password complexity + account lockout (Redis-based) | `users.py`, `auth.py`, `rate_limit.py` | **HIGH** |

---

## Хураангуй хүснэгт

| Түвшин | Тоо | Гол асуудлууд |
|--------|-----|---------------|
| **CRITICAL** | 6 | Hardcoded JWT, SQL injection хэв маяг, AI model missing silent fail, RTSP password HTTP дамжуулалт |
| **HIGH** | 6 | CORS creds+wildcard, HS256, password complexity байхгүй, account lockout байхгүй, worker-based rate limiter |
| **MEDIUM** | 8 | Unauthenticated endpoint-үүд, token query string-д, refresh token хүчингүй болохгүй |
| **LOW** | 11 | Root container, exposed DB/Redis ports, MediaMTX open auth, MD5 digest |

### Бидний хийсэн өөрчлөлтүүдийн аюулгүй байдлын үнэлгээ

| Өөрчлөлт | Үнэлгээ |
|----------|---------|
| `config_service.py` — timezone функц | ✅ `ZoneInfo()` IANA-р баталгаажсан, fallback аюулгүй |
| `counter_service.py` — timezone-р query хийх | ✅ Утгууд параметрчлагдсан, WHERE pattern нь хуучин хэв маяг |
| `frame_sampler.py` — tz параметр | ✅ `ZoneInfo` төрөл, default аюулгүй |
| `main.py` — DB-с timezone унших | ✅ `read_config_str` утгыг `ZoneInfo` хүртэл нь шалгадаг |
| `db.py` — `read_config_str` | ⚠️ Буцаах утгыг sanitize хийхгүй (гэхдээ хэрэглэгч бүрт `ZoneInfo` дотор exception) |
| Migration SQL | ✅ `make_interval()` — SQL injection байхгүй, pure DML |
| `ConfigSection.tsx` — frontend | ✅ Зөвхөн fixed dropdown option-ууд, injection хийх боломжгүй |
