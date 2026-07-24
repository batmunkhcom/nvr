# NVR — Системийг бүхэлд нь сайжруулах мастер төлөвлөгөө

> Үүсгэсэн: 2026-07-24
> Төлөв: 🟢 Идэвхтэй — дэс дараагаар гүйцэтгэж байна
> Ажил бүрийн дараа commit + push хийнэ. Төлвийг `[x]` гэж тэмдэглэнэ.

---

## 0. Шинжилгээний дүгнэлт (2026-07-24)

### Серверийн нөөц
| Нөөц | Байдал | Үнэлгээ |
|------|--------|---------|
| Диск | 29GB нийт, **9.6GB чөлөөтэй (66% дүүрсэн)** | 🔴 Критик — бичлэг хийх бараг зайгүй |
| RAM | 7.8GB, 3.6GB ашиглагдаж | 🟡 Хангалттай |
| CPU | 4 core, stream-manager 131% | 🟡 Тranscode ачаалал өндөр |
| Docker | images 10GB + build cache 4.5GB | 🔴 Цэвэрлэх шаардлагатай |

### Илэрсэн критик асуудлууд
| # | Асуудал | Үр дагавар |
|---|---------|-----------|
| C1 | `nvr-recording-engine` container **ажиллахгүй** | Бичлэг огт байхгүй (0 recording) |
| C2 | `nvr-ai-engine` container **ажиллахгүй** | AI танилт огт ажиллахгүй — машин өнгөрөөд ч танигдахгүй |
| C3 | `ai_models` volume **хоосон** — yolov8n.onnx байхгүй | AI engine асаасан ч model load fail |
| C4 | `detector.py` YOLOv8 output parsing **буруу** (YOLOv5 format-аар уншина), NMS байхгүй | Model байсан ч detection буруу/хоосон |
| C5 | `recording-engine` env mismatch: compose `DB_USER/DB_NAME` өгдөг, код `POSTGRES_USER/POSTGRES_DB` уншина | DB холбогдож чадахгүй |
| C6 | `recording-engine` нууц үг тайлалт Fernet ашигладаг — системийн бусад хэсэг AES-256-GCM (`NVR_ENCRYPTION_KEY`) | Камерын нууц үг тайлагдахгүй → бичлэг fail |
| C7 | `main.py` retention дуудалт `RetentionManager(session)` — TypeError (аргумент авдаггүй) | Retention хэзээ ч ажиллахгүй → диск дүүрнэ |
| C8 | Диск дүүрэхэд хуучныг дарж бичдэг (circular) механизм **байхгүй** | Диск дүүрээд систем унана |
| C9 | `health_check_loop` баг: `probe_ip() got an unexpected keyword argument 'port'` — 10 камер бүрт алдаа | Health check ажиллахгүй |
| C10 | Docker json-log rotation тохируулагдаагүй | Лог диск дүүргэх эрсэлтэй |
| C11 | `ai.confidence_threshold` = "2" (буруу утга, 0–1 байх ёстой) | Танилт шүүлт буруу |
| C12 | `retention.default_days` = 30 хоног — 29GB дискэнд физик боломжгүй | Тооцоолол буруу |

### Дискийн тооцоолол (10 камер)
| Стрим | Bitrate | 1 камер/хоног | 10 камер/хоног | 9.6GB-эд багтах хоног |
|-------|---------|---------------|----------------|----------------------|
| Main (камер шууд ~4.9Mbps) | 4.9 Mbps | ~53 GB | ~530 GB | ❌ боломжгүй |
| Main (MediaMTX transcode 2Mbps) | 2 Mbps | ~21.6 GB | ~216 GB | ❌ боломжгүй |
| **Sub-stream (~512kbps)** | 0.5 Mbps | **~5.4 GB** | **~54 GB** | ~1.5 хоног |
| Sub-stream багассан (~256kbps) | 0.25 Mbps | ~2.7 GB | ~27 GB | ~3 хоног |

**Шийдэл**: Sub-stream бичлэг + circular retention (диск дүүрэхэд хамгийн хуучныг автомат устгал) + GB/хоног хэмжилт.

---

## Phase 1 — Диск аюулгүй байдал (Яаралтай) ✅

- [x] **1.1** Docker цэвэрлэх: build cache 4.5GB чөлөөлсөн (9.6GB → 13GB чөлөөтэй)
- [x] **1.2** Docker log rotation бүх 13 service-д (`max-size: 10m, max-file: 3`)
- [x] **1.3** Recordings disk budget тохиргоо: `storage.max_usage_percent`=85, `storage.min_free_gb`=2, `recording.segment_seconds`=300, `recording.stream`=sub; retention 30→7 хоног (бодитой)

## Phase 2 — Recording engine бүрэн ажиллагаатай 🟡

- [x] **2.1** Env mismatch засах: compose `POSTGRES_*` нэршил рүү нэгдмэл болгосон (код хоёуланг нь уншина)
- [x] **2.2** Нууц үг тайлалт AES-256-GCM — `nvr_common.security` shared module үүсгэсэн (Fernet устгасан)
- [x] **2.3** Retention wiring TypeError засах — бүтэн шинэ retention.py (plain SQL)
- [x] **2.4** **Circular retention**: дискийн watermark (85% эсвэл <2GB чөлөө) хэтэрвэл хамгийн хуучин сегментээс устгана; 10 минутаас шинэ файл хамгаалагдсан; DB sync
- [x] **2.5** Recorder → `recordings` table: SegmentCatalog 60с тутам scan → шинэ сегмент DB-д бүртгэнэ (ffprobe duration), устсан файлуудын мөрийг цэвэрлэнэ
- [x] **2.6** Sub-stream бичлэг + `-c:v copy` + 300с сегмент (config-аас уншина)
- [x] **2.7** Recording container ажиллаж байна ✅ — 10/10 камер бичиж байна (live баталгаажуулсан: query string, date dirs, ffmpeg timeout засварууд хийгдсэн). API-аар тоглуулалт ажиллана (token query param нэмсэн)
- [x] **2.8** **Диск хэрэглээний анализ**: `storage.analysis` config-д цаг тутам тооцдог (GB/хоног, days_fit). Хэмжилт: ~26GB/хоног (10 камер sub-stream). Storage UI-д харуулах үлдлээ
- [x] **2.9** Тест: test_recording_engine.py 12 тест pass ✅

## Phase 3 — AI танилт бүрэн ажиллагаатай 🟡

- [x] **3.1** Compose env засах: POSTGRES_* credentials, NVR_ENCRYPTION_KEY, STORAGE_LOCAL_PATH, recordings volume (snapshots), restart policy, command/working_dir
- [ ] **3.2** YOLOv8n ONNX model татах → `ai_models` volume (ai-engine image доторх ultralytics-аар export)
- [x] **3.3** `detector.py` бүрэн шинэчилсэн: YOLOv8 `(1,84,8400)` → transpose, per-class argmax, confidence filter, **cv2.dnn.NMSBoxes**, letterbox unscale; shared singleton session
- [x] **3.4** Cooldown баг засах: `_apply_cooldown` одоо үнэхээр шүүдэг (class тус бүрээр, 15с)
- [x] **3.5** Frame pipeline сайжруулалт: JPEG round-trip устгасан (numpy direct), cap.read/inference thread-д, reconnect backoff 5→120с
- [x] **3.6** `ai.confidence_threshold` 2→0.5 зассан (DB) + кодод clamp validation (0.05–0.95)
- [x] **3.7** AI container ажиллаж байна ✅ — **машин (0.55) ба хүн (0.73) танигдсан** live баталгаажуулалттай, snapshot-ууд хадгалагдаж байна. Position-aware dedup нэмсэн (зогсож буй машин 5 мин тутам 1 event)
- [x] **3.8** Events UI: snapshot thumbnail (token auth-тай), объект badge (машин/хүн icon), камер шүүлтүүр — бичигдсэн ✅
- [x] **3.9** Тест: test_ai_engine.py 14 тест (URL build, confidence clamp, cooldown, letterbox) — numpy-тэй орчинд ажиллана

## Phase 4 — Performance & tuning ✅

- [x] **4.1** `health_check_loop` `probe_ip(port=)` баг зассан + live_relay тестүүд шинэчилсэн (59/59 pass)
- [x] **4.1b** LiveViewPage тестүүд зассан: PTZ товчуудад title нэмсэн, HLS mock MANIFEST_PARSED-тэй, useStreamPlayer-д errorMsg state + fail-fast нэмсэн (34/34 frontend pass)
- [x] **4.2** stream-manager: **idle reaper** — 10 мин үзэгчгүй (MediaMTX readers=0) relay-г зогсооно (CPU хэмнэнэ). MediaMTX API auth зассан (v1.19 internal users)
- [x] **4.3** DB индекс: `events(camera_id, start_time DESC)`, `events(start_time DESC)`, `recordings(camera_id, start_time DESC)` — alembic 0008
- [x] **4.4** Compose: `restart: unless-stopped` бүх үндсэн service-д (7 шинэ + 2)
- [x] **4.5** FFmpeg segment 300с болгосон (config `recording.segment_seconds`)

## Phase 5 — Дизайн & хэрэглэгчийн зааварчилгаа ✅ (гол хэсэг)

- [x] **5.1** Design token систем — index.css-д surface/semantic/typography tokens + dark scrollbar + page transitions (өмнөх ажлаас бэлэн байсан)
- [x] **5.2** Toast notification систем — `components/ui/Toast.tsx` бэлэн байсан, ConfigSection-д ашиглагддаг
- [x] **5.3** **Settings хуудас бүрэн функционал**: storage.* категори, select input, DB description-аас монгол тайлбар уншидэг (13 key монгол тайлбартай) + англи fallback
- [x] **5.4** Form тайлбарууд: Camera Add/Edit (бүх талбарт hint: sub-stream яагаад хэрэгтэй, нууц үг encrypt, AI source г.м.)
- [x] **5.5** Storage хуудас: Recording Disk Analysis card (GB/хоног, ~хоног багтах projection, камер бүрийн хүснэгт, circular тайлбар)
- [ ] **5.6** Empty states polish (бэлэн EmptyState компонент байгаа — нэмэлт сайжруулалт хожим)
- [ ] **5.7** Camera tile status ring + connection error tooltip (backlog)

## Phase 6 — Баримт бичиг эцсийн 🟡

- [x] **6.1** `AGENTS.md` шинэчлэх: recording flow, AI flow, circular retention, idle reaper, key files
- [x] **6.2** `docs/work-status.md` — доорх session summary-гаар шинэчилсэн
- [ ] **6.3** `README.md` шинэчлэх (recording/AI идэвхтэй төлөв тусгах)
- [x] **6.4** Энэхүү файлын төлвийг байнга шинэчлэж байна

---

## Үлдэх backlog (дараагийн ажил)

- [ ] Motion-only бичлэг (AI event-тэй холбосон) — одоо continuous л ажилладаг
- [ ] AI zones (polygon) UI
- [ ] Telegram/webhook мэдэгдэл идэвхжүүлэлт (notification_service бэлэн)
- [ ] Storage backend mount-ууд (NFS/S3) — recordings volume-г том диск рүү зөөх
- [ ] Дискийг физик өргөтгөх (одоо 29GB — ~0.5 хоногийн бичлэг л багтана; 26GB/хоног хэрэглээтэй)

---

## Гүйцэтгэлийн лог

| Огноо | Ажил | Төлөв |
|-------|------|-------|
| 2026-07-24 | Системийн бүтэн шинжилгээ, төлөвлөгөө үүсгэх | ✅ |
| 2026-07-24 | Phase 1: Docker цэвэрлэх (4.5GB), log rotation, disk budget config | ✅ |
| 2026-07-24 | Phase 2: recording-engine бүрэн шинэчлэл — 10/10 камер бичиж байна, circular retention LIVE баталгаажсан (76 сегмент устгаж 1.08GB чөлөөлсөн), DB бүртгэл, диск анализ | ✅ |
| 2026-07-24 | Phase 3: ai-engine бүрэн шинэчлэл — **машин/хүн танигддаг болсон**, YOLOv8n ONNX export, position-aware dedup, Events UI | ✅ |
| 2026-07-24 | Phase 4: idle reaper, MediaMTX API auth, DB indexes, restart policies, health check баг, LiveViewPage тест | ✅ |
| 2026-07-24 | Phase 5: Settings storage категори + монгол тайлбарууд, camera form hints, Storage analysis card | ✅ |
| 2026-07-24 | Phase 6: AGENTS.md, work-status шинэчлэл | ✅ |
