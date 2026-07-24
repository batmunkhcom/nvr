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

## Phase 1 — Диск аюулгүй байдал (Яаралтай) ⬜

- [ ] **1.1** Docker цэвэрлэх: build cache (~4.5GB), ашиглагдаагүй images (~3.2GB) → ~8GB чөлөөлөх
- [ ] **1.2** Docker log rotation бүх service-д (`max-size: 10m, max-file: 3`)
- [ ] **1.3** Recordings disk budget тохиргоо: `storage.max_usage_percent` (default 85%), `storage.min_free_gb` (default 2GB) system_config-д

## Phase 2 — Recording engine бүрэн ажиллагаатай ⬜

- [ ] **2.1** Env mismatch засах: compose `POSTGRES_*` нэршилтэй болгох (эсвэл код `DB_*` унших) — аль алийг нэгдмэл болгох
- [ ] **2.2** Нууц үг тайлалтыг `app.core.security.decrypt_password_aes` (AES-256-GCM) руу шилжүүлэх — Fernet устгах
- [ ] **2.3** Retention wiring TypeError засах (`RetentionManager(session)` → зөв signature)
- [ ] **2.4** **Circular retention**: дискийн чөлөөт зай watermark-аас доошлохөд хамгийн хуучин сегментээс эхэлж устгах (диск хэзээ ч дүүрэхгүй, overwrite oldest). DB мөрийг файлтай sync байлгах
- [ ] **2.5** Recorder → `recordings` table бүртгэл: сегмент бичигдэх бүрд DB мөр үүсгэх (Recordings хуудас одоо хоосон харагдаж байна)
- [ ] **2.6** Sub-stream бичлэг: `stream_sub_uri`-аар бичих (диск 10x хэмнэнэ), `-c:v copy` (CPU хэмнэнэ)
- [ ] **2.7** Recording container асаах, сегмент бичигдэж байгааг баталгаажуулах (`/data/recordings/...`), Recordings хуудаснаас тоглуулж үзэх
- [ ] **2.8** **Диск хэрэглээний анализ**: камер тус бүрийн бодит bitrate → GB/хоног хэмжилт, system_config-д хадгалах, Storage хуудсанд "X GB/хоног, ~Y хоногийн бичлэг багтана" гэж харуулах
- [ ] **2.9** Тест: retention unit test (circular устгалтын дараалал), recorder segment DB registration test

## Phase 3 — AI танилт бүрэн ажиллагаатай ⬜

- [ ] **3.1** Compose env засах: ai-engine-д DB credentials, STORAGE_LOCAL_PATH, snapshots volume mount нэмэх
- [ ] **3.2** YOLOv8n ONNX model татах → `ai_models` volume (entrypoint-д auto-download, интернетгүй бол local fallback)
- [ ] **3.3** `detector.py` бүрэн засах: YOLOv8 output `(1,84,8400)` → transpose, per-class argmax, confidence filter, **NMS**, letterbox координат буцаалт
- [ ] **3.4** Cooldown баг засах: cooldown-д байгаа class-уудыг persist хийхээс өмнө шүүх (одоо шүүлтүүргүйгээр бүгдийг хадгалдаг)
- [ ] **3.5** Frame source: MediaMTX sub relay (`rtsp://nvr-mediamtx:8554/{id}_sub`) ашиглах — камерт нэмэлт холболт үүсгэхгүй; fallback: шууд камер
- [ ] **3.6** `ai.confidence_threshold` = 2 буруу утгыг 0.5 болгох; validation нэмэх (0–1 хүрээ)
- [ ] **3.7** AI container асаах, машин/хүн танигдаж events + snapshots үүсэж байгааг баталгаажуулах
- [ ] **3.8** Events UI: snapshot thumbnail, объект төрлийн badge, шүүлтүүр (камер/төрөл/огноо)
- [ ] **3.9** Тест: detector post-processing unit test (fixture tensor), NMS test

## Phase 4 — Performance & tuning ⬜

- [ ] **4.1** `health_check_loop` `probe_ip(port=)` баг засах — 10 камерын auto status сэргээх
- [ ] **4.2** stream-manager CPU аудит: 15 идэвхтэй стрим 131% — dashboard зөвхөн sub татаж байгаа шалгах, relay auto-stop хугацаа тохируулах
- [ ] **4.3** DB индекс: `events(camera_id, start_time)`, `recordings(camera_id, start_time)` шалгах/нэмэх; PostgreSQL tuning (shared_buffers 512MB, effective_cache_size 4GB)
- [ ] **4.4** Compose: бүх app service-д `restart: unless-stopped`, healthcheck нэмэх (api, stream-manager, recording, ai)
- [ ] **4.5** FFmpeg segment параметр tuning: `-segment_time 900` → 300 (5 мин — устгал нарийн, сэргээлт хурдан)

## Phase 5 — Дизайн & хэрэглэгчийн зааварчилгаа ⬜

- [ ] **5.1** Design token систем: surface/accent/success/warning/danger тодорхойлж, орчин үеийн цэвэрхэн dark theme
- [ ] **5.2** Toast notification систем (`alert()`/`confirm()` бүрэн солих)
- [ ] **5.3** **Settings хуудас бүрэн функционал**: бүх system_config утгыг визуал formaар засах + **тохиргоо бүрт монгол тайлбар** (юунд хэрэгтэй, ямар утга зөв гэдгийг)
- [ ] **5.4** Бүх form-д тайлбар текст: камер нэмэх/засах (RTSP URI гэж юу вэ, sub-stream яагаад хэрэгтэй вэ), discovery, schedule, storage, users
- [ ] **5.5** Storage хуудас: дискийн график, GB/хоног, retention projection, circular горимын төлөв
- [ ] **5.6** Empty states + skeleton loading сайжруулалт
- [ ] **5.7** Dark scrollbar, page transition fade, typography scale

## Phase 6 — Баримт бичиг эцсийн ⬜

- [ ] **6.1** `AGENTS.md` шинэчлэх: recording flow, AI flow, circular retention, disk budget
- [ ] **6.2** `docs/work-status.md` эцсийн байдлаар шинэчлэх
- [ ] **6.3** `README.md` шинэчлэх (recording/AI идэвхтэй төлөв тусгах)
- [ ] **6.4** Энэхүү файлын төлвийг байнга шинэчлэх

---

## Гүйцэтгэлийн лог

| Огноо | Ажил | Төлөв | Commit |
|-------|------|-------|--------|
| 2026-07-24 | Системийн бүтэн шинжилгээ, төлөвлөгөө үүсгэх | ✅ | — |
